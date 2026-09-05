# Changelog

## [0.2.0](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.1.0...wiz2mqtt-v0.2.0) (2026-09-05)


### ⚠ BREAKING CHANGES

* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error — it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))
* **wiz2mqtt:** canonical hue/saturation colour model ([#218](https://github.com/ff-fab/cosalette-apps/issues/218)) ([c37aff6](https://github.com/ff-fab/cosalette-apps/commit/c37aff61ea2d5055cffe9681dbf39ec2a2adf81b))
* **wiz2mqtt:** command handling — partial updates and mutual exclusion ([9cf174c](https://github.com/ff-fab/cosalette-apps/commit/9cf174c7396d38000cd79295aa51dfbc0851e74f))
* **wiz2mqtt:** scaffold the app ([#213](https://github.com/ff-fab/cosalette-apps/issues/213)) ([6c374c6](https://github.com/ff-fab/cosalette-apps/commit/6c374c6a0d9b837438db88aa1d9bfe37533f8058))
* **wiz2mqtt:** settings and TOML bulb inventory ([#217](https://github.com/ff-fab/cosalette-apps/issues/217)) ([30b9836](https://github.com/ff-fab/cosalette-apps/commit/30b98361df67bf68cf18bd6bf93238cda64a4cc8))
* **wiz2mqtt:** state publication and availability debounce ([661f317](https://github.com/ff-fab/cosalette-apps/commit/661f3179bc383f0058a84d038edab00541dfd07b))
* **wiz2mqtt:** WizBulbPort adapter — push, state cache, capability detection ([#216](https://github.com/ff-fab/cosalette-apps/issues/216)) ([3ecc23d](https://github.com/ff-fab/cosalette-apps/commit/3ecc23d1e29941adf2b90cf5012cf74f4ac15b31))


### Bug Fixes

* **build:** scaffold-app.sh anchor/schema gaps and wiz2mqtt env wiring ([#214](https://github.com/ff-fab/cosalette-apps/issues/214)) ([6bf27f6](https://github.com/ff-fab/cosalette-apps/commit/6bf27f60d1e2023e4e4b174f1a85a45cea5e3161))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))


### Documentation

* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* **wiz2mqtt:** fix cross-site ADR link and document publication behaviour ([#226](https://github.com/ff-fab/cosalette-apps/issues/226)) ([5b3f2e6](https://github.com/ff-fab/cosalette-apps/commit/5b3f2e6c76d7a4821c12329926610c40408586d5))

## Changelog
