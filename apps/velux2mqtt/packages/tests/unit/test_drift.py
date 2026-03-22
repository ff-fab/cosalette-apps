"""Unit tests for DriftCompensator."""

from velux2mqtt.domain.drift import DriftCompensator, MoveStep


class TestDirectMoves:
    """Test moves that don't trigger recalibration."""

    def test_endpoint_move_is_always_direct(self) -> None:
        """Moving to 0 or 100 is always a single step."""
        dc = DriftCompensator(threshold=2)
        assert dc.plan_move(50.0, 0) == [MoveStep(target=0)]
        assert dc.plan_move(50.0, 100) == [MoveStep(target=100)]

    def test_first_intermediate_is_direct(self) -> None:
        """First intermediate move doesn't trigger recalibration."""
        dc = DriftCompensator(threshold=2)
        result = dc.plan_move(0.0, 20)
        assert result == [MoveStep(target=20)]
        assert dc.consecutive_intermediate == 1

    def test_second_intermediate_is_direct(self) -> None:
        """Second intermediate move is still under threshold."""
        dc = DriftCompensator(threshold=2)
        dc.plan_move(0.0, 20)
        result = dc.plan_move(20.0, 40)
        assert result == [MoveStep(target=40)]
        assert dc.consecutive_intermediate == 2


class TestRecalibration:
    """Test moves that trigger recalibration."""

    def test_third_intermediate_triggers_recalibration(self) -> None:
        """Third consecutive intermediate move triggers recalibration."""
        dc = DriftCompensator(threshold=2)

        # Move 1: 0% → 20%
        dc.plan_move(0.0, 20)
        # Move 2: 20% → 40%
        dc.plan_move(20.0, 40)
        # Move 3: 40% → 80% — should recalibrate
        result = dc.plan_move(40.0, 80)

        assert len(result) == 2
        assert result[0].is_recalibration is True
        assert result[1].target == 80
        assert result[1].is_recalibration is False

    def test_optimal_endpoint_close(self) -> None:
        """When closer to 0%, recalibrates via close endpoint."""
        dc = DriftCompensator(threshold=2)
        dc.plan_move(0.0, 20)
        dc.plan_move(20.0, 30)

        # At ~30%, going to 80%:
        # via 0: |30-0| + |0-80| = 30 + 80 = 110
        # via 100: |30-100| + |100-80| = 70 + 20 = 90 → better
        result = dc.plan_move(30.0, 80)
        assert result[0].target == 100

    def test_optimal_endpoint_open(self) -> None:
        """When closer to 100%, recalibrates via open endpoint."""
        dc = DriftCompensator(threshold=2)
        dc.plan_move(100.0, 80)
        dc.plan_move(80.0, 70)

        # At ~70%, going to 20%:
        # via 0: |70-0| + |0-20| = 70 + 20 = 90
        # via 100: |70-100| + |100-20| = 30 + 80 = 110
        # → via 0 is better
        result = dc.plan_move(70.0, 20)
        assert result[0].target == 0

    def test_user_scenario_open_20_40_80(self) -> None:
        """Full scenario from the analysis: open → 20% → 40% → 80%.

        HA semantics: 0=closed, 100=open.
        Starting at 100% (fully open).
        """
        dc = DriftCompensator(threshold=2)

        # Step 1: 100% → 20% (first intermediate)
        r1 = dc.plan_move(100.0, 20)
        assert r1 == [MoveStep(target=20)]

        # Step 2: 20% → 40% (second intermediate, still under threshold)
        r2 = dc.plan_move(20.0, 40)
        assert r2 == [MoveStep(target=40)]

        # Step 3: 40% → 80% (third intermediate, triggers recalibration)
        r3 = dc.plan_move(40.0, 80)
        assert len(r3) == 2
        assert r3[0].is_recalibration is True
        # via 0: |40-0| + |0-80| = 120
        # via 100: |40-100| + |100-80| = 80 → pick 100
        assert r3[0].target == 100
        assert r3[1].target == 80


class TestCounterReset:
    """Test counter reset on endpoint arrival."""

    def test_endpoint_resets_counter(self) -> None:
        """Moving to an endpoint resets the consecutive counter."""
        dc = DriftCompensator(threshold=2)
        dc.plan_move(0.0, 20)
        dc.plan_move(20.0, 40)
        assert dc.consecutive_intermediate == 2

        dc.plan_move(40.0, 100)  # endpoint
        assert dc.consecutive_intermediate == 0

    def test_recalibration_resets_counter(self) -> None:
        """After recalibration, counter reflects only the final move."""
        dc = DriftCompensator(threshold=2)
        dc.plan_move(0.0, 20)
        dc.plan_move(20.0, 40)
        dc.plan_move(40.0, 80)  # triggers recalibration

        # Counter should be 1 (the final move to 80 counts)
        assert dc.consecutive_intermediate == 1


class TestThresholdEdgeCases:
    """Test threshold boundary conditions."""

    def test_threshold_zero_disables(self) -> None:
        """With threshold=0, recalibration never triggers."""
        dc = DriftCompensator(threshold=0)
        for _ in range(10):
            result = dc.plan_move(50.0, 42)
            assert len(result) == 1

    def test_threshold_one(self) -> None:
        """With threshold=1, second intermediate triggers recalibration."""
        dc = DriftCompensator(threshold=1)
        dc.plan_move(0.0, 50)  # first intermediate
        result = dc.plan_move(50.0, 30)  # second → recalibrate
        assert len(result) == 2
        assert result[0].is_recalibration is True

    def test_explicit_reset(self) -> None:
        """reset() clears the counter."""
        dc = DriftCompensator(threshold=2)
        dc.plan_move(0.0, 20)
        dc.plan_move(20.0, 40)
        dc.reset()
        assert dc.consecutive_intermediate == 0
