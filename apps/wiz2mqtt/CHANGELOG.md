# Changelog

## [0.2.3](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.2...wiz2mqtt-v0.2.3) (2026-09-13)


### Features

* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))

## [0.2.2](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.1...wiz2mqtt-v0.2.2) (2026-09-12)


### Bug Fixes

* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))


### Documentation

* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))

## [0.2.1](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.0...wiz2mqtt-v0.2.1) (2026-09-08)


### Features

* **wiz2mqtt:** add discover CLI for LAN bulb onboarding (cap-10u.15) ([#240](https://github.com/ff-fab/cosalette-apps/issues/240)) ([a8e0d1b](https://github.com/ff-fab/cosalette-apps/commit/a8e0d1bd8d000801aedcb9db64242728bb6929fd))
* **wiz2mqtt:** consumer integration — runtime HA discovery and openHAB generation ([#238](https://github.com/ff-fab/cosalette-apps/issues/238)) ([36589bf](https://github.com/ff-fab/cosalette-apps/commit/36589bf3854b89138d730d167f9dfa818ceca8d9))
* **wiz2mqtt:** generate consumer bulb groups ([#243](https://github.com/ff-fab/cosalette-apps/issues/243)) ([ea4de28](https://github.com/ff-fab/cosalette-apps/commit/ea4de28e028d7e0acf4dfc18e37826741d97f59d))
* **wiz2mqtt:** per-bulb capability-filtered HA discovery (cap-3tr) ([#241](https://github.com/ff-fab/cosalette-apps/issues/241)) ([3bbb122](https://github.com/ff-fab/cosalette-apps/commit/3bbb1227581e028dc1d07fe869b4ca51853833bc))
* **wiz2mqtt:** ship host networking for WiZ push (cap-10u.16) ([#239](https://github.com/ff-fab/cosalette-apps/issues/239)) ([5a3c87b](https://github.com/ff-fab/cosalette-apps/commit/5a3c87b37b676d0cea4ff23bb551f0385b6d208d))

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
