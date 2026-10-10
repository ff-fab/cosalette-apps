# Changelog

## [0.2.14](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.13...wiz2mqtt-v0.2.14) (2026-10-10)


### Bug Fixes

* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* **wiz2mqtt:** reconnect observability, direct commands during reconnect, image smoke tests ([#372](https://github.com/ff-fab/cosalette-apps/issues/372)) ([7f07c4d](https://github.com/ff-fab/cosalette-apps/commit/7f07c4da829445bc66d83a7f8e352da3d256a0fe))
* **wiz2mqtt:** restore a quick power cycle that missed no poll ([#371](https://github.com/ff-fab/cosalette-apps/issues/371)) ([f237418](https://github.com/ff-fab/cosalette-apps/commit/f23741825bb67deebbe252642cc70ef221848f22))
* **wiz2mqtt:** restore white/CT-mode state and stop reverting user commands ([#367](https://github.com/ff-fab/cosalette-apps/issues/367)) ([665b9eb](https://github.com/ff-fab/cosalette-apps/commit/665b9eb4f3be147976be62933f419f1a95a59239))
* **wiz2mqtt:** ship PyYAML so wiz2mqtt-openhab works in the image ([#364](https://github.com/ff-fab/cosalette-apps/issues/364)) ([0110984](https://github.com/ff-fab/cosalette-apps/commit/0110984ca794551e170fb2db954ad7385dd172f1))
* **wiz2mqtt:** stop spurious firstBeat restores and replay one colour mode ([#368](https://github.com/ff-fab/cosalette-apps/issues/368)) ([f7b6e5b](https://github.com/ff-fab/cosalette-apps/commit/f7b6e5b696b5ebb797d776f3cd0711c2b613bbb5))

## [0.2.13](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.12...wiz2mqtt-v0.2.13) (2026-10-09)


### Features

* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* **wiz2mqtt:** adopt native health probe ([#346](https://github.com/ff-fab/cosalette-apps/issues/346)) ([ce3625a](https://github.com/ff-fab/cosalette-apps/commit/ce3625a83242d61103fc363fed60d8088ca73a5c))


### Bug Fixes

* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))

## [0.2.12](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.11...wiz2mqtt-v0.2.12) (2026-10-04)


### Features

* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))


### Bug Fixes

* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))

## [0.2.11](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.10...wiz2mqtt-v0.2.11) (2026-10-04)


### Bug Fixes

* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))

## [0.2.10](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.9...wiz2mqtt-v0.2.10) (2026-10-02)


### Features

* **wiz2mqtt:** pace restore retries and confirm every colour restore ([#312](https://github.com/ff-fab/cosalette-apps/issues/312)) ([70c578a](https://github.com/ff-fab/cosalette-apps/commit/70c578a84273513e578963c58f18855e1b1fd6d6))


### Bug Fixes

* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))

## [0.2.9](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.8...wiz2mqtt-v0.2.9) (2026-09-30)


### Bug Fixes

* **wiz2mqtt:** harden power and HSB commands ([#311](https://github.com/ff-fab/cosalette-apps/issues/311)) ([c136d42](https://github.com/ff-fab/cosalette-apps/commit/c136d42f5da614ca5872fb7480a097e59a947306))
* **wiz2mqtt:** stabilize return-path restore ([#309](https://github.com/ff-fab/cosalette-apps/issues/309)) ([c798d7d](https://github.com/ff-fab/cosalette-apps/commit/c798d7d0d172bb0c339ba6dfb16c064df2dde8b2))

## [0.2.8](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.7...wiz2mqtt-v0.2.8) (2026-09-30)


### Features

* **wiz2mqtt:** add switched-relay boot safeguards ([#308](https://github.com/ff-fab/cosalette-apps/issues/308)) ([3912e05](https://github.com/ff-fab/cosalette-apps/commit/3912e059c8f4d084201ac56cb46e3cd88180b65a))
* **wiz2mqtt:** expose queued-command readiness state ([#307](https://github.com/ff-fab/cosalette-apps/issues/307)) ([17dd7e3](https://github.com/ff-fab/cosalette-apps/commit/17dd7e31439803c9efeee7dd851400cee7d6a95f))
* **wiz2mqtt:** full openHAB channels, power-request contract, OFF fixes ([#306](https://github.com/ff-fab/cosalette-apps/issues/306)) ([64ece03](https://github.com/ff-fab/cosalette-apps/commit/64ece03bac3cf121c95ec9932ce8799ff76a7807))


### Bug Fixes

* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))

## [0.2.7](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.6...wiz2mqtt-v0.2.7) (2026-09-28)


### Bug Fixes

* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))

## [0.2.6](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.5...wiz2mqtt-v0.2.6) (2026-09-25)


### Bug Fixes

* **wiz2mqtt:** round fractional numbers on the .../set command fields ([#299](https://github.com/ff-fab/cosalette-apps/issues/299)) ([019cb55](https://github.com/ff-fab/cosalette-apps/commit/019cb55e4cb2a40f633acbcebc1d7acf62e76621))

## [0.2.5](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.4...wiz2mqtt-v0.2.5) (2026-09-19)


### Features

* **vito2mqtt,wallpanel-control,wiz2mqtt:** opt in to MQTT 5 retained-message expiry ([#284](https://github.com/ff-fab/cosalette-apps/issues/284)) ([be74719](https://github.com/ff-fab/cosalette-apps/commit/be7471967ef5310a254782fc61026a8d3a3ade48))
* **wiz2mqtt:** add power-source settings and fake adapter test controls ([#276](https://github.com/ff-fab/cosalette-apps/issues/276)) ([75bc3ee](https://github.com/ff-fab/cosalette-apps/commit/75bc3eea0fe8c9e8b941e9e55cd2709456a61358))
* **wiz2mqtt:** boot signal, desired state, command queue, power belief ([#278](https://github.com/ff-fab/cosalette-apps/issues/278)) ([7f8abe1](https://github.com/ff-fab/cosalette-apps/commit/7f8abe1f8ad4071523f902b4efbf0938cb2be5c9))
* **wiz2mqtt:** generate openHAB power source items and per-bulb powered ([#296](https://github.com/ff-fab/cosalette-apps/issues/296)) ([1887436](https://github.com/ff-fab/cosalette-apps/commit/1887436ebccc2ac58e6e80f4be96d8a479541af0))
* **wiz2mqtt:** publish retained power requests per source ([#295](https://github.com/ff-fab/cosalette-apps/issues/295)) ([613883f](https://github.com/ff-fab/cosalette-apps/commit/613883fdcb6c1211d25a82e26ddabd3ea2c2a440))
* **wiz2mqtt:** restore desired state on return to reachability ([#279](https://github.com/ff-fab/cosalette-apps/issues/279)) ([31498f5](https://github.com/ff-fab/cosalette-apps/commit/31498f5423404f80a766c2c20d98e74ebbf5413b))
* **wiz2mqtt:** skip reads on a known-off power source, announce it in HA discovery ([#280](https://github.com/ff-fab/cosalette-apps/issues/280)) ([41d0366](https://github.com/ff-fab/cosalette-apps/commit/41d0366280feda56173efb7125dee13e7920326d))
* **wiz2mqtt:** subscribe to power-source signals with cosalette inbound (closes cap-pnjx) ([#286](https://github.com/ff-fab/cosalette-apps/issues/286)) ([cf07555](https://github.com/ff-fab/cosalette-apps/commit/cf0755568be10a2572115361e2e0e676f3bb449e))


### Bug Fixes

* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#288](https://github.com/ff-fab/cosalette-apps/issues/288)) ([f40153d](https://github.com/ff-fab/cosalette-apps/commit/f40153d26633c6b4fdc9b704a002169dcceebbf8))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **wiz2mqtt:** turn the belief off at once on a relay signal 'off' ([#298](https://github.com/ff-fab/cosalette-apps/issues/298)) ([3912f43](https://github.com/ff-fab/cosalette-apps/commit/3912f43c9ebcd033b6a476c14dd27e0b4fa73c93))


### Documentation

* **wiz2mqtt:** document mains power awareness for operators and consumers ([#297](https://github.com/ff-fab/cosalette-apps/issues/297)) ([f10db18](https://github.com/ff-fab/cosalette-apps/commit/f10db18cc01452c9295570f47331eff32223afcf))

## [0.2.4](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.2.3...wiz2mqtt-v0.2.4) (2026-09-16)


### Bug Fixes

* **wiz2mqtt:** clear superseded colour mode on optimistic state merge ([#270](https://github.com/ff-fab/cosalette-apps/issues/270)) ([3eb5c64](https://github.com/ff-fab/cosalette-apps/commit/3eb5c6437ab51924e753e885e113a44543239f2f))
* **wiz2mqtt:** diagnose and retry a failed push registration ([#273](https://github.com/ff-fab/cosalette-apps/issues/273)) ([e4e4c69](https://github.com/ff-fab/cosalette-apps/commit/e4e4c690b4ca2dcb82adff6a65eb3b5e0f8fcd29))
* **wiz2mqtt:** harden bulb first contact ([#269](https://github.com/ff-fab/cosalette-apps/issues/269)) ([62c3d2d](https://github.com/ff-fab/cosalette-apps/commit/62c3d2de303918c5090953f3ed1bb7abe8ea956f))
* **wiz2mqtt:** probe with the bulb's own clock so the heartbeat liveness check is real ([#272](https://github.com/ff-fab/cosalette-apps/issues/272)) ([60d2d14](https://github.com/ff-fab/cosalette-apps/commit/60d2d144547c079f7a2c46247116d18b72be385b))
* **wiz2mqtt:** set WIZ2MQTT_STORE_PATH so the capability cache survives recreation ([#271](https://github.com/ff-fab/cosalette-apps/issues/271)) ([2a6defa](https://github.com/ff-fab/cosalette-apps/commit/2a6defa61b135ce12e79fea9ddcaa3638f9cf82a))


### Documentation

* **wiz2mqtt:** record mains power awareness ADRs and plan the epic ([#267](https://github.com/ff-fab/cosalette-apps/issues/267)) ([dd0d842](https://github.com/ff-fab/cosalette-apps/commit/dd0d84285114e80ec460d58ff62c6eb3a3cc5c13))

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
