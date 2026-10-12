:robot: I have created a release *beep* *boop*
---


<details><summary>jeelink2mqtt: 0.4.0</summary>

## [0.4.0](https://github.com/ff-fab/cosalette-apps/compare/jeelink2mqtt-v0.3.0...jeelink2mqtt-v0.4.0) (2026-10-12)


###   BREAKING CHANGES

* error topic payloads follow cosalette 0.12.0 (ADR-091). A timed-out handler (`error_type` `timeout`) now publishes the message `TimeoutError` instead of an empty or library-provided message, and `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored unless the app opts in (only wiz2mqtt and wallpanel-control do). Check this release's app-specific notes for further operator actions.
* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error  it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* add adapter resilience ([60547a7](https://github.com/ff-fab/cosalette-apps/commit/60547a7c52b298f4c425be5437e7f66b02499a4e))
* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))
* allow verbose error opt-in fleet-wide and settle cosalette 0.12.0 error disclosure (cap-mzz4) ([#402](https://github.com/ff-fab/cosalette-apps/issues/402)) ([1af9f8b](https://github.com/ff-fab/cosalette-apps/commit/1af9f8b7998810a84f5c5398f986891e852eba4e))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration  contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* **docs:** add header breadcrumb linking app docs to monorepo root ([d62851d](https://github.com/ff-fab/cosalette-apps/commit/d62851db69839bd2830b629d5a72ef09cd9519c3))
* **docs:** add mkdocs-click-zoom plugin to all documentation sites ([#70](https://github.com/ff-fab/cosalette-apps/issues/70)) ([21c85ec](https://github.com/ff-fab/cosalette-apps/commit/21c85ece8667ba3a7a46d738c1c24847e985a8a9))
* **docs:** add per-app version display to docs sites ([#34](https://github.com/ff-fab/cosalette-apps/issues/34)) ([d355c0e](https://github.com/ff-fab/cosalette-apps/commit/d355c0e8dbe440af2bdcb0f242859a4f2ea02e3b))
* **docs:** shared doc assets + header breadcrumb for app sites ([4e57caf](https://github.com/ff-fab/cosalette-apps/commit/4e57caf09f8db1de4d891536c8f62905c9c10b29))
* **docs:** sync light/dark palette across all documentation sites ([#42](https://github.com/ff-fab/cosalette-apps/issues/42)) ([ad7daeb](https://github.com/ff-fab/cosalette-apps/commit/ad7daeb8e2ff1d02e29590ac33d6e4db33b332e4))
* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* **jeelink2mqtt,suncast,velux2mqtt:** opt in to MQTT 5 retained-message expiry ([#283](https://github.com/ff-fab/cosalette-apps/issues/283)) ([d28e035](https://github.com/ff-fab/cosalette-apps/commit/d28e035b3a36cd3f8ff66b9b251e979ba7dcfca2))
* **jeelink2mqtt:** adopt receiver freshness, stale exit and native health probe ([#336](https://github.com/ff-fab/cosalette-apps/issues/336)) ([0e09609](https://github.com/ff-fab/cosalette-apps/commit/0e096097abc2e4ca08de78c600b9f1da438ef955))
* **jeelink2mqtt:** adopt runtime Home Assistant discovery ([#235](https://github.com/ff-fab/cosalette-apps/issues/235)) ([41d900c](https://github.com/ff-fab/cosalette-apps/commit/41d900c8d0918b6a32c41c184a48ee0db807fbe9))
* **jeelink2mqtt:** migrate jeelink2mqtt into monorepo ([#6](https://github.com/ff-fab/cosalette-apps/issues/6)) ([87574c2](https://github.com/ff-fab/cosalette-apps/commit/87574c2f10fa7598295d312f781dec03664e8ac8))
* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))


### Bug Fixes

* address PR review  restore thread-safety and loop resilience ([b9b3d41](https://github.com/ff-fab/cosalette-apps/commit/b9b3d4120bba307c223e18c9d1b2cac152819e6b))
* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))
* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))
* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* **docs:** replace symlinks with pre-build copy for shared assets ([a0b8243](https://github.com/ff-fab/cosalette-apps/commit/a0b82436d55f63f650892d7163d2ecc0b7400c73))
* **docs:** replace symlinks with pre-build copy for shared assets ([#40](https://github.com/ff-fab/cosalette-apps/issues/40)) ([483e35f](https://github.com/ff-fab/cosalette-apps/commit/483e35f40ee684e4726df38e2e9752e48a211160))
* **jeelink2mqtt:** drop stale telemetry-only restart_on_stale claim ([a20baae](https://github.com/ff-fab/cosalette-apps/commit/a20baae32021ef4abc9e6a72cc4acb8fe93d77aa))
* **jeelink2mqtt:** remove error-swallowing in LaCrosse adapter ([e410a23](https://github.com/ff-fab/cosalette-apps/commit/e410a234fa2e063849f4dbb1cca7904429f22367))
* **jeelink2mqtt:** restart stale receiver ([#339](https://github.com/ff-fab/cosalette-apps/issues/339)) ([215c194](https://github.com/ff-fab/cosalette-apps/commit/215c1948fcac0d5454b263404ab4210a4c0cdef5))
* **jeelink2mqtt:** restart stale receiver in place before exit backstop ([#340](https://github.com/ff-fab/cosalette-apps/issues/340)) ([4669c53](https://github.com/ff-fab/cosalette-apps/commit/4669c536701557cfb2ce83476efadc7e9b65474d))
* persist state across container recreation for jeelink2mqtt and gas2mqtt ([#274](https://github.com/ff-fab/cosalette-apps/issues/274)) ([8fc24ec](https://github.com/ff-fab/cosalette-apps/commit/8fc24ec78122ce99f6f1830c89fb72ad79e63bbf))
* remove error-swallowing in device handlers ([ee46221](https://github.com/ff-fab/cosalette-apps/commit/ee46221a44c8ea4a0b060066a40dd3ef37bfc5e8))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))
* **taskfiles:** ignore GPL header in per-app similarity gate (cap-9dr) ([#185](https://github.com/ff-fab/cosalette-apps/issues/185)) ([dab2396](https://github.com/ff-fab/cosalette-apps/commit/dab2396e998a7fce2cd8d0b26cabe86adb59559c))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))
* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))
* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))
* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))
* upgrade to cosalette 0.12.0 ([e544dfc](https://github.com/ff-fab/cosalette-apps/commit/e544dfc0b30891432a623b0cbfcc39ccf380100d))


### Documentation

* add zoomable docs images ([#92](https://github.com/ff-fab/cosalette-apps/issues/92)) ([0b14b99](https://github.com/ff-fab/cosalette-apps/commit/0b14b9975b1504fb52e2af1819d1de8ebf0ac9c9))
* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))
</details>

<details><summary>vito2mqtt: 0.4.0</summary>

## [0.4.0](https://github.com/ff-fab/cosalette-apps/compare/vito2mqtt-v0.3.0...vito2mqtt-v0.4.0) (2026-10-12)


###   BREAKING CHANGES

* error topic payloads follow cosalette 0.12.0 (ADR-091). A timed-out handler (`error_type` `timeout`) now publishes the message `TimeoutError` instead of an empty or library-provided message, and `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored unless the app opts in (only wiz2mqtt and wallpanel-control do). Check this release's app-specific notes for further operator actions.
* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error  it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* add adapter resilience ([60547a7](https://github.com/ff-fab/cosalette-apps/commit/60547a7c52b298f4c425be5437e7f66b02499a4e))
* add Docker deployment infrastructure ([#19](https://github.com/ff-fab/cosalette-apps/issues/19)) ([accb046](https://github.com/ff-fab/cosalette-apps/commit/accb046566aab643583bca35d0e219ab6ea318ef))
* add unavailable_on to command handlers ([#171](https://github.com/ff-fab/cosalette-apps/issues/171)) ([b6142b3](https://github.com/ff-fab/cosalette-apps/commit/b6142b338355505fad2ec63c7f32e16038cb43c1))
* adopt App.discovery() runtime HA discovery across apps ([8ccd74d](https://github.com/ff-fab/cosalette-apps/commit/8ccd74d87509b32e5238d9b9e55d263e25ba609a))
* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))
* allow verbose error opt-in fleet-wide and settle cosalette 0.12.0 error disclosure (cap-mzz4) ([#402](https://github.com/ff-fab/cosalette-apps/issues/402)) ([1af9f8b](https://github.com/ff-fab/cosalette-apps/commit/1af9f8b7998810a84f5c5398f986891e852eba4e))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration  contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* **docs:** add header breadcrumb linking app docs to monorepo root ([d62851d](https://github.com/ff-fab/cosalette-apps/commit/d62851db69839bd2830b629d5a72ef09cd9519c3))
* **docs:** add mkdocs-click-zoom plugin to all documentation sites ([#70](https://github.com/ff-fab/cosalette-apps/issues/70)) ([21c85ec](https://github.com/ff-fab/cosalette-apps/commit/21c85ece8667ba3a7a46d738c1c24847e985a8a9))
* **docs:** add per-app version display to docs sites ([#34](https://github.com/ff-fab/cosalette-apps/issues/34)) ([d355c0e](https://github.com/ff-fab/cosalette-apps/commit/d355c0e8dbe440af2bdcb0f242859a4f2ea02e3b))
* **docs:** shared doc assets + header breadcrumb for app sites ([4e57caf](https://github.com/ff-fab/cosalette-apps/commit/4e57caf09f8db1de4d891536c8f62905c9c10b29))
* **docs:** sync light/dark palette across all documentation sites ([#42](https://github.com/ff-fab/cosalette-apps/issues/42)) ([ad7daeb](https://github.com/ff-fab/cosalette-apps/commit/ad7daeb8e2ff1d02e29590ac33d6e4db33b332e4))
* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* HA discovery schema enrichment for wallpanel-control + vito2mqtt (cap-3bz Phase 2) ([#181](https://github.com/ff-fab/cosalette-apps/issues/181)) ([34abe9c](https://github.com/ff-fab/cosalette-apps/commit/34abe9cf36dc879296bb189597d91aae17a52805))
* implement adapter layer (ports & adapters) ([#6](https://github.com/ff-fab/cosalette-apps/issues/6)) ([50b1697](https://github.com/ff-fab/cosalette-apps/commit/50b1697d41c9cce2625096bfd8d4d383f7f37986))
* implement command handlers for writable parameters ([#11](https://github.com/ff-fab/cosalette-apps/issues/11)) ([a658c69](https://github.com/ff-fab/cosalette-apps/commit/a658c69c28f9fb8c09259f090e922e4eb820dc68))
* implement Optolink P300 protocol layer ([#5](https://github.com/ff-fab/cosalette-apps/issues/5)) ([cfe3417](https://github.com/ff-fab/cosalette-apps/commit/cfe34179aa0cf7cb07141fc9dee81d580c85cfa4))
* implement telemetry devices (all 7 signal groups) ([#9](https://github.com/ff-fab/cosalette-apps/issues/9)) ([301f09b](https://github.com/ff-fab/cosalette-apps/commit/301f09baf37b5c821ea19d09415291fe7ab9c2ad))
* integrate coalescing groups for telemetry handlers ([e43c7d2](https://github.com/ff-fab/cosalette-apps/commit/e43c7d20742afa66ce222234886a674a122f2cd4))
* integrate coalescing groups for telemetry handlers ([1d94e5a](https://github.com/ff-fab/cosalette-apps/commit/1d94e5aafef5e82f387625a96d9d9523d288fce4))
* legionella treatment feature ([#15](https://github.com/ff-fab/cosalette-apps/issues/15)) ([3a57e8b](https://github.com/ff-fab/cosalette-apps/commit/3a57e8b445fe3ac77ddc010b2a9d8ca96ad1bdf6))
* make store path configurable via VITO2MQTT_STORE_PATH ([#22](https://github.com/ff-fab/cosalette-apps/issues/22)) ([c54c9ee](https://github.com/ff-fab/cosalette-apps/commit/c54c9eeb14a3303db38c1da5bdf19aadb6121f7d))
* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* read-before-write optimization for command handlers ([#13](https://github.com/ff-fab/cosalette-apps/issues/13)) ([21b2ef8](https://github.com/ff-fab/cosalette-apps/commit/21b2ef8a28e3e0d01c92b6259f5c748f4bf9b7c6))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))
* **vito2mqtt,wallpanel-control,wiz2mqtt:** opt in to MQTT 5 retained-message expiry ([#284](https://github.com/ff-fab/cosalette-apps/issues/284)) ([be74719](https://github.com/ff-fab/cosalette-apps/commit/be7471967ef5310a254782fc61026a8d3a3ade48))
* **vito2mqtt:** adopt native health probe ([#342](https://github.com/ff-fab/cosalette-apps/issues/342)) ([b7d9205](https://github.com/ff-fab/cosalette-apps/commit/b7d9205007aae3c14a654dda0cdccec6e0023df6))
* **vito2mqtt:** migrate vito2mqtt into monorepo ([4a607a7](https://github.com/ff-fab/cosalette-apps/commit/4a607a7274d37798e92df392ee0f8a8f6a72e810))
* **vito2mqtt:** migrate vito2mqtt into monorepo ([06facd6](https://github.com/ff-fab/cosalette-apps/commit/06facd6bb52cc292ecfc7094b09259d923634a80))
* **wallpanel-control:** adopt native health probe ([#343](https://github.com/ff-fab/cosalette-apps/issues/343)) ([2238135](https://github.com/ff-fab/cosalette-apps/commit/223813583d7e0efd6c684f973e267ae2f8091946))
* wire app composition root with CLI entry point ([#12](https://github.com/ff-fab/cosalette-apps/issues/12)) ([7aecc81](https://github.com/ff-fab/cosalette-apps/commit/7aecc816b97f7ceda37e0c016e31ac572554fcc9))


### Bug Fixes

* allow --help/--version without env vars ([#14](https://github.com/ff-fab/cosalette-apps/issues/14)) ([a2867e8](https://github.com/ff-fab/cosalette-apps/commit/a2867e81562a2e8d130b5a0b31cf5b9deaba5f98))
* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))
* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* delegate Dolt server lifecycle to bd dolt start ([#8](https://github.com/ff-fab/cosalette-apps/issues/8)) ([118f8ba](https://github.com/ff-fab/cosalette-apps/commit/118f8ba8ae43796a962ada89006a40b81ae00bd0))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))
* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* **docs:** replace symlinks with pre-build copy for shared assets ([a0b8243](https://github.com/ff-fab/cosalette-apps/commit/a0b82436d55f63f650892d7163d2ecc0b7400c73))
* **docs:** replace symlinks with pre-build copy for shared assets ([#40](https://github.com/ff-fab/cosalette-apps/issues/40)) ([483e35f](https://github.com/ff-fab/cosalette-apps/commit/483e35f40ee684e4726df38e2e9752e48a211160))
* harden CI app-name validation and batch vito2mqtt serial writes ([#174](https://github.com/ff-fab/cosalette-apps/issues/174)) ([070769e](https://github.com/ff-fab/cosalette-apps/commit/070769eeeb33a5473f9d0b54c96e4b9b8554e93e))
* ignore .env.* files and correct vito2mqtt topic docs ([#285](https://github.com/ff-fab/cosalette-apps/issues/285)) ([7fcc572](https://github.com/ff-fab/cosalette-apps/commit/7fcc5720320d045a9510bdc8580f1a26b9ebcc06))
* record cosalette 0.9.3 framework baseline across remaining apps ([#248](https://github.com/ff-fab/cosalette-apps/issues/248)) ([3d32433](https://github.com/ff-fab/cosalette-apps/commit/3d324332d61320e0439d24383dbf18235b2b6dd5))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))
* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))
* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))
* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))
* upgrade to cosalette 0.12.0 ([e544dfc](https://github.com/ff-fab/cosalette-apps/commit/e544dfc0b30891432a623b0cbfcc39ccf380100d))
* **vito2mqtt:** align Dockerfile with monorepo pattern and fix doc payloads ([3572895](https://github.com/ff-fab/cosalette-apps/commit/3572895e63d2701cb04c68baf0561d9762e75633))
* **vito2mqtt:** remove unused device_id setting ([#290](https://github.com/ff-fab/cosalette-apps/issues/290)) ([13b7025](https://github.com/ff-fab/cosalette-apps/commit/13b70252496bba308fe141df94d010d217015897))


### Reverts

* undo direct commits to main (use PR instead) ([a385bd1](https://github.com/ff-fab/cosalette-apps/commit/a385bd1bc61460bcc82598e66062794059ebad0a))


### Documentation

* add 5 foundational ADRs for vito2mqtt architecture ([4d60e14](https://github.com/ff-fab/cosalette-apps/commit/4d60e1424fc7d70777ae4364e05959d3bd1abe18))
* add 5 foundational ADRs for vito2mqtt architecture ([75ba017](https://github.com/ff-fab/cosalette-apps/commit/75ba0174a872a628a23eec1ac8ffd0c488ea2995))
* add ADR-006 configurable signal language (DE/EN) ([d64b297](https://github.com/ff-fab/cosalette-apps/commit/d64b297a4d97938254e4591974faeb67cc7ceeb6))
* add ADR-006 configurable signal language (DE/EN) ([9d8b9a2](https://github.com/ff-fab/cosalette-apps/commit/9d8b9a21b933e37e10bfb0f8478a4442d7ee6bb6))
* add ADR-007 coalescing groups and framework requirements ([fa9d59f](https://github.com/ff-fab/cosalette-apps/commit/fa9d59fbc842dde0341fa0023fc59d6b4850e38a))
* add complete documentation site ([#16](https://github.com/ff-fab/cosalette-apps/issues/16)) ([57bd640](https://github.com/ff-fab/cosalette-apps/commit/57bd6407a69506f42af1551cbbd20dbab8cf628a))
* add zoomable docs images ([#92](https://github.com/ff-fab/cosalette-apps/issues/92)) ([0b14b99](https://github.com/ff-fab/cosalette-apps/commit/0b14b9975b1504fb52e2af1819d1de8ebf0ac9c9))
* address PR review comments ([dc18fcd](https://github.com/ff-fab/cosalette-apps/commit/dc18fcddcc349904eabb57be530f2d33fdff326f))
* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* fix mode count, error count, and pipe rendering in ADR-006 ([dc8aa3f](https://github.com/ff-fab/cosalette-apps/commit/dc8aa3f3853bfb8667e0cb14a14c8714a7c6dc83))
* refine context section in ADR-006 for clarity ([9da4f95](https://github.com/ff-fab/cosalette-apps/commit/9da4f95adbfce31cfb9115ee0fc833cc7dfd34bf))
* **vito2mqtt:** document the instance id for multiple instances ([#345](https://github.com/ff-fab/cosalette-apps/issues/345)) ([a545a7e](https://github.com/ff-fab/cosalette-apps/commit/a545a7ed9729a33306081f1aafec0fcb9030e893))
* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))
</details>

<details><summary>velux2mqtt: 0.4.0</summary>

## [0.4.0](https://github.com/ff-fab/cosalette-apps/compare/velux2mqtt-v0.3.0...velux2mqtt-v0.4.0) (2026-10-12)


###   BREAKING CHANGES

* error topic payloads follow cosalette 0.12.0 (ADR-091). A timed-out handler (`error_type` `timeout`) now publishes the message `TimeoutError` instead of an empty or library-provided message, and `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored unless the app opts in (only wiz2mqtt and wallpanel-control do). Check this release's app-specific notes for further operator actions.
* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error  it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* add adapter resilience ([60547a7](https://github.com/ff-fab/cosalette-apps/commit/60547a7c52b298f4c425be5437e7f66b02499a4e))
* adopt App.discovery() runtime HA discovery across apps ([8ccd74d](https://github.com/ff-fab/cosalette-apps/commit/8ccd74d87509b32e5238d9b9e55d263e25ba609a))
* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))
* allow verbose error opt-in fleet-wide and settle cosalette 0.12.0 error disclosure (cap-mzz4) ([#402](https://github.com/ff-fab/cosalette-apps/issues/402)) ([1af9f8b](https://github.com/ff-fab/cosalette-apps/commit/1af9f8b7998810a84f5c5398f986891e852eba4e))
* **caldates2mqtt:** add typed state_model as HA-discovery prep (cap-wxg) ([733e954](https://github.com/ff-fab/cosalette-apps/commit/733e95430bdfc5f3cb4c7f7c2a8ee40b144b7161))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration  contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* **docs:** add mkdocs-click-zoom plugin to all documentation sites ([#70](https://github.com/ff-fab/cosalette-apps/issues/70)) ([21c85ec](https://github.com/ff-fab/cosalette-apps/commit/21c85ece8667ba3a7a46d738c1c24847e985a8a9))
* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* HA discovery schema enrichment for gas2mqtt + velux2mqtt (cap-3bz Phase 1) ([#180](https://github.com/ff-fab/cosalette-apps/issues/180)) ([fe1d3cb](https://github.com/ff-fab/cosalette-apps/commit/fe1d3cbb41384e481a5faf5fdbc153a5fffbe2de))
* **jeelink2mqtt,suncast,velux2mqtt:** opt in to MQTT 5 retained-message expiry ([#283](https://github.com/ff-fab/cosalette-apps/issues/283)) ([d28e035](https://github.com/ff-fab/cosalette-apps/commit/d28e035b3a36cd3f8ff66b9b251e979ba7dcfca2))
* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))
* **velux2mqtt:** add calibration state machine ([#46](https://github.com/ff-fab/cosalette-apps/issues/46)) ([3fc11f1](https://github.com/ff-fab/cosalette-apps/commit/3fc11f1ad59450983eda6dd5f61002c9348595c0))
* **velux2mqtt:** add dead band support for handle travel ([#51](https://github.com/ff-fab/cosalette-apps/issues/51)) ([a75e6b3](https://github.com/ff-fab/cosalette-apps/commit/a75e6b37d55ac280b92f83dc6d65ebec51cb0036))
* **velux2mqtt:** adopt native health probe ([#341](https://github.com/ff-fab/cosalette-apps/issues/341)) ([8de3bed](https://github.com/ff-fab/cosalette-apps/commit/8de3bed7bd64e45c89f364a54f0ec2e16ed2557d))
* **velux2mqtt:** core documentation and direction-aware calibration ([#54](https://github.com/ff-fab/cosalette-apps/issues/54)) ([2371af0](https://github.com/ff-fab/cosalette-apps/commit/2371af011a90980b3b5afa196704919a30de5bfc))
* **velux2mqtt:** cover device handler, homing, and main.py wiring ([#45](https://github.com/ff-fab/cosalette-apps/issues/45)) ([c5de30e](https://github.com/ff-fab/cosalette-apps/commit/c5de30e2862381329754a4de51ef366950ff2f85))
* **velux2mqtt:** make offset measurement optional during calibration ([#52](https://github.com/ff-fab/cosalette-apps/issues/52)) ([c518503](https://github.com/ff-fab/cosalette-apps/commit/c518503ebd8c5fff7443596a1af4640d72f9680d))
* **velux2mqtt:** measure travel_time_offset during calibration ([#50](https://github.com/ff-fab/cosalette-apps/issues/50)) ([509d762](https://github.com/ff-fab/cosalette-apps/commit/509d7626d50ae9eb45b62802423223f47322ef0b))
* **velux2mqtt:** scaffold app and implement domain logic ([#43](https://github.com/ff-fab/cosalette-apps/issues/43)) ([0be0b83](https://github.com/ff-fab/cosalette-apps/commit/0be0b8374c9c1f84c06ee64512d8088c68b41826))
* **velux2mqtt:** wire calibration into cover device handler ([#47](https://github.com/ff-fab/cosalette-apps/issues/47)) ([8a77327](https://github.com/ff-fab/cosalette-apps/commit/8a77327b64d2336553b49825b829935730bf714f))
* **wallpanel-control:** implement adapters and test fixtures ([f337856](https://github.com/ff-fab/cosalette-apps/commit/f3378569fe7eba58107f17d407657da3c65eb54c))


### Bug Fixes

* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))
* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))
* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* record cosalette 0.9.3 framework baseline across remaining apps ([#248](https://github.com/ff-fab/cosalette-apps/issues/248)) ([3d32433](https://github.com/ff-fab/cosalette-apps/commit/3d324332d61320e0439d24383dbf18235b2b6dd5))
* resolve cosalette 0.5.1 ephemeral-store warning for store-less apps ([#167](https://github.com/ff-fab/cosalette-apps/issues/167)) ([e67b97c](https://github.com/ff-fab/cosalette-apps/commit/e67b97c054e39a7c40802d573a5ac848fe6a0204))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))
* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))
* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))
* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))
* upgrade to cosalette 0.12.0 ([e544dfc](https://github.com/ff-fab/cosalette-apps/commit/e544dfc0b30891432a623b0cbfcc39ccf380100d))
* **velux2mqtt:** replace fixed wall-clock waits with condition polling in calibration test helper ([#211](https://github.com/ff-fab/cosalette-apps/issues/211)) ([db9bab1](https://github.com/ff-fab/cosalette-apps/commit/db9bab17f0423209ebaed7b638a155fa5c255d56))
* **velux2mqtt:** replace run_app_briefly's fixed wait with poll-based startup settling ([#212](https://github.com/ff-fab/cosalette-apps/issues/212)) ([86e5f82](https://github.com/ff-fab/cosalette-apps/commit/86e5f82a0440d0c457001a69ee3c15895450f1b2))
* **velux2mqtt:** skip STOP press for endpoint moves ([#55](https://github.com/ff-fab/cosalette-apps/issues/55)) ([fe7eb86](https://github.com/ff-fab/cosalette-apps/commit/fe7eb86031ecb368787913fc6961e1b4e1e2a6fe))
* **velux2mqtt:** stop shipping phantom HA-discovery entity ([#201](https://github.com/ff-fab/cosalette-apps/issues/201)) ([733e954](https://github.com/ff-fab/cosalette-apps/commit/733e95430bdfc5f3cb4c7f7c2a8ee40b144b7161))


### Documentation

* add zoomable docs images ([#92](https://github.com/ff-fab/cosalette-apps/issues/92)) ([0b14b99](https://github.com/ff-fab/cosalette-apps/commit/0b14b9975b1504fb52e2af1819d1de8ebf0ac9c9))
* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* homogenise app documentation with top-bar nav and rich homepages ([#63](https://github.com/ff-fab/cosalette-apps/issues/63)) ([8394409](https://github.com/ff-fab/cosalette-apps/commit/83944090729b7bd413755a8ba6bfab163216dc2f))
* update cosalette badge with custom icon and fix click-zoom assets ([faa3724](https://github.com/ff-fab/cosalette-apps/commit/faa37245bd384edb3579b42433bac4b387de4fd5))
* **velux2mqtt:** add configuration reference and .env.example ([#53](https://github.com/ff-fab/cosalette-apps/issues/53)) ([a281efb](https://github.com/ff-fab/cosalette-apps/commit/a281efba972bb1a3e8dae453a71dccdb0de0fbb6))
* **velux2mqtt:** add wiring diagram, getting-started guide, and framework proposals ([#57](https://github.com/ff-fab/cosalette-apps/issues/57)) ([146e76b](https://github.com/ff-fab/cosalette-apps/commit/146e76b790703ce64033917b290e2ffb3ae9d512))
* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))
</details>

<details><summary>airthings2mqtt: 0.5.0</summary>

## [0.5.0](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.4.0...airthings2mqtt-v0.5.0) (2026-10-12)


###   BREAKING CHANGES

* error topic payloads follow cosalette 0.12.0 (ADR-091). A timed-out handler (`error_type` `timeout`) now publishes the message `TimeoutError` instead of an empty or library-provided message, and `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored unless the app opts in (only wiz2mqtt and wallpanel-control do). Check this release's app-specific notes for further operator actions.
* **airthings2mqtt:** the host needs a system account for UID 10001, because dbus-daemon refuses connections from a UID without a host account, and existing data volumes or bind mounts must be chowned to 10001:10001. See docs/host-setup.md.
* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error  it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* add adapter resilience ([60547a7](https://github.com/ff-fab/cosalette-apps/commit/60547a7c52b298f4c425be5437e7f66b02499a4e))
* adopt App.discovery() runtime HA discovery across apps ([8ccd74d](https://github.com/ff-fab/cosalette-apps/commit/8ccd74d87509b32e5238d9b9e55d263e25ba609a))
* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))
* **airthings2mqtt,caldates2mqtt,gas2mqtt:** opt in to MQTT 5 retained-message expiry ([#282](https://github.com/ff-fab/cosalette-apps/issues/282)) ([d3e07da](https://github.com/ff-fab/cosalette-apps/commit/d3e07da88145058433b0f88fc5a40a87a1b3ceb0))
* **airthings2mqtt:** add last_read and rssi to the state payload ([#321](https://github.com/ff-fab/cosalette-apps/issues/321)) ([d68a664](https://github.com/ff-fab/cosalette-apps/commit/d68a66479415c17cf0c975bcb3ceaace4f768c8b))
* **airthings2mqtt:** add pre-connect advertiser scan ([dc8e103](https://github.com/ff-fab/cosalette-apps/commit/dc8e103c7c1bd685cb71ddebd230dc03d445c1b7))
* **airthings2mqtt:** adopt native health probe ([#348](https://github.com/ff-fab/cosalette-apps/issues/348)) ([dff6285](https://github.com/ff-fab/cosalette-apps/commit/dff62856b272fcf3e8e5b4ee86a1fdc77f5c18b9))
* **airthings2mqtt:** cosalette 0.11 freshness, health check, dedicated UID and host D-Bus hardening ([#323](https://github.com/ff-fab/cosalette-apps/issues/323)) ([8ecaafb](https://github.com/ff-fab/cosalette-apps/commit/8ecaafbc1755729bcb42e551089ec2c33c100efa))
* **airthings2mqtt:** detect sensor reset, withhold radon placeholders, publish measurement_state ([#324](https://github.com/ff-fab/cosalette-apps/issues/324)) ([e6ebfab](https://github.com/ff-fab/cosalette-apps/commit/e6ebfabdb013ef490fe98708496e1fed834b0ea1))
* **airthings2mqtt:** scaffold app with settings, BLE adapters, and tests ([#59](https://github.com/ff-fab/cosalette-apps/issues/59)) ([8025428](https://github.com/ff-fab/cosalette-apps/commit/802542859ff9b83b296beb81aa370eb810c4bb35))
* **airthings2mqtt:** support the Wave 2 / Wave Radon (2nd-gen) BLE protocol ([#234](https://github.com/ff-fab/cosalette-apps/issues/234)) ([3fe4b62](https://github.com/ff-fab/cosalette-apps/commit/3fe4b62ca59c584b0c5af788b019eec04853954d))
* **airthings2mqtt:** support triggerable rereads ([#129](https://github.com/ff-fab/cosalette-apps/issues/129)) ([e56f907](https://github.com/ff-fab/cosalette-apps/commit/e56f9075f443e5ddc05e98f20316b0b4c53554bc))
* **airthings2mqtt:** telemetry device handler with full test coverage ([#61](https://github.com/ff-fab/cosalette-apps/issues/61)) ([7bd1556](https://github.com/ff-fab/cosalette-apps/commit/7bd1556b957305bfb19668f1bb50276144ea9a7d))
* allow verbose error opt-in fleet-wide and settle cosalette 0.12.0 error disclosure (cap-mzz4) ([#402](https://github.com/ff-fab/cosalette-apps/issues/402)) ([1af9f8b](https://github.com/ff-fab/cosalette-apps/commit/1af9f8b7998810a84f5c5398f986891e852eba4e))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration  contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* **docs:** add mkdocs-click-zoom plugin to all documentation sites ([#70](https://github.com/ff-fab/cosalette-apps/issues/70)) ([21c85ec](https://github.com/ff-fab/cosalette-apps/commit/21c85ece8667ba3a7a46d738c1c24847e985a8a9))
* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))
* **wallpanel-control:** implement adapters and test fixtures ([f337856](https://github.com/ff-fab/cosalette-apps/commit/f3378569fe7eba58107f17d407657da3c65eb54c))


### Bug Fixes

* **airthings2mqtt:** declare BLE reader not restartable; ADR-003 no adapter power-cycling ([#322](https://github.com/ff-fab/cosalette-apps/issues/322)) ([1eedda3](https://github.com/ff-fab/cosalette-apps/commit/1eedda3434e338000c20d5866be27f7ccef2bd46))
* **airthings2mqtt:** drop the bluez package from the image ([#354](https://github.com/ff-fab/cosalette-apps/issues/354)) ([d941a7c](https://github.com/ff-fab/cosalette-apps/commit/d941a7cf2c22b4798da340fa2a79ba9e490d66af))
* **airthings2mqtt:** redact BLE MAC in log + make health_check async ([#144](https://github.com/ff-fab/cosalette-apps/issues/144)) ([ed5b027](https://github.com/ff-fab/cosalette-apps/commit/ed5b0278bb6b1ecf0b1c8d7c51ab2ca6c5ce2034))
* **airthings2mqtt:** retry and redact BLE device-not-found failures (early-adopter feedback) ([#316](https://github.com/ff-fab/cosalette-apps/issues/316)) ([b97fce1](https://github.com/ff-fab/cosalette-apps/commit/b97fce1d1ee7aff26b2babf904c39571828bdd94))
* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))
* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))
* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* record cosalette 0.9.3 framework baseline across remaining apps ([#248](https://github.com/ff-fab/cosalette-apps/issues/248)) ([3d32433](https://github.com/ff-fab/cosalette-apps/commit/3d324332d61320e0439d24383dbf18235b2b6dd5))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))
* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))
* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))
* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))
* upgrade to cosalette 0.12.0 ([e544dfc](https://github.com/ff-fab/cosalette-apps/commit/e544dfc0b30891432a623b0cbfcc39ccf380100d))


### Documentation

* add zoomable docs images ([#92](https://github.com/ff-fab/cosalette-apps/issues/92)) ([0b14b99](https://github.com/ff-fab/cosalette-apps/commit/0b14b9975b1504fb52e2af1819d1de8ebf0ac9c9))
* **airthings2mqtt:** add documentation and deployment config ([#62](https://github.com/ff-fab/cosalette-apps/issues/62)) ([4518fef](https://github.com/ff-fab/cosalette-apps/commit/4518fefa5887e1d3752497438999f09f0ed81b07))
* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* homogenise app documentation with top-bar nav and rich homepages ([#63](https://github.com/ff-fab/cosalette-apps/issues/63)) ([8394409](https://github.com/ff-fab/cosalette-apps/commit/83944090729b7bd413755a8ba6bfab163216dc2f))
* update cosalette badge with custom icon and fix click-zoom assets ([faa3724](https://github.com/ff-fab/cosalette-apps/commit/faa37245bd384edb3579b42433bac4b387de4fd5))
* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))
</details>

<details><summary>caldates2mqtt: 0.4.0</summary>

## [0.4.0](https://github.com/ff-fab/cosalette-apps/compare/caldates2mqtt-v0.3.0...caldates2mqtt-v0.4.0) (2026-10-12)


###   BREAKING CHANGES

* error topic payloads follow cosalette 0.12.0 (ADR-091). A timed-out handler (`error_type` `timeout`) now publishes the message `TimeoutError` instead of an empty or library-provided message, and `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored unless the app opts in (only wiz2mqtt and wallpanel-control do). Check this release's app-specific notes for further operator actions.
* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error  it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))
* **airthings2mqtt,caldates2mqtt,gas2mqtt:** opt in to MQTT 5 retained-message expiry ([#282](https://github.com/ff-fab/cosalette-apps/issues/282)) ([d3e07da](https://github.com/ff-fab/cosalette-apps/commit/d3e07da88145058433b0f88fc5a40a87a1b3ceb0))
* allow verbose error opt-in fleet-wide and settle cosalette 0.12.0 error disclosure (cap-mzz4) ([#402](https://github.com/ff-fab/cosalette-apps/issues/402)) ([1af9f8b](https://github.com/ff-fab/cosalette-apps/commit/1af9f8b7998810a84f5c5398f986891e852eba4e))
* **caldates2mqtt:** add retry/backoff to calendar fetch ([#138](https://github.com/ff-fab/cosalette-apps/issues/138)) ([20dbb94](https://github.com/ff-fab/cosalette-apps/commit/20dbb949f8a47b1b9ebc1c1545049eace70dd3ae))
* **caldates2mqtt:** add typed state_model as HA-discovery prep (cap-wxg) ([733e954](https://github.com/ff-fab/cosalette-apps/commit/733e95430bdfc5f3cb4c7f7c2a8ee40b144b7161))
* **caldates2mqtt:** adopt native health probe and loop-stall watchdog ([#335](https://github.com/ff-fab/cosalette-apps/issues/335)) ([1d67c2c](https://github.com/ff-fab/cosalette-apps/commit/1d67c2c1f592bbfd546e858889f730c7ecd8a8e1))
* **caldates2mqtt:** adopt runtime HA discovery (cap-2qg, cap-gsd) ([#258](https://github.com/ff-fab/cosalette-apps/issues/258)) ([10ab611](https://github.com/ff-fab/cosalette-apps/commit/10ab6113f73f714456119cc5f85040809dbf3ead))
* **caldates2mqtt:** carry the event list as HA attributes (cap-6hw) ([#257](https://github.com/ff-fab/cosalette-apps/issues/257)) ([2f4d517](https://github.com/ff-fab/cosalette-apps/commit/2f4d517ef4261cdbcb8fdaf0a790f6d6aecf87c0))
* **caldates2mqtt:** convert to triggerable telemetry ([#109](https://github.com/ff-fab/cosalette-apps/issues/109)) ([bababd8](https://github.com/ff-fab/cosalette-apps/commit/bababd8eaf25ae4199b0d82640a8f28c2224725d))
* **caldates2mqtt:** expose events as a portable count aggregate (cap-p09) ([#259](https://github.com/ff-fab/cosalette-apps/issues/259)) ([0dd1963](https://github.com/ff-fab/cosalette-apps/commit/0dd1963b5d6f734d29d615a17ec071a8c70a1d10))
* **caldates2mqtt:** scaffold app with settings, adapters, device handler ([#66](https://github.com/ff-fab/cosalette-apps/issues/66)) ([b5f1dda](https://github.com/ff-fab/cosalette-apps/commit/b5f1dda7230975c01a1674e210c62014988408a7))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration  contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* **docs:** add mkdocs-click-zoom plugin to all documentation sites ([#70](https://github.com/ff-fab/cosalette-apps/issues/70)) ([21c85ec](https://github.com/ff-fab/cosalette-apps/commit/21c85ece8667ba3a7a46d738c1c24847e985a8a9))
* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))
* **wallpanel-control:** implement adapters and test fixtures ([f337856](https://github.com/ff-fab/cosalette-apps/commit/f3378569fe7eba58107f17d407657da3c65eb54c))


### Bug Fixes

* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* **caldates2mqtt:** resolve smoke-test findings A-1 and A-2 ([#163](https://github.com/ff-fab/cosalette-apps/issues/163)) ([86f29e9](https://github.com/ff-fab/cosalette-apps/commit/86f29e929e909a455ba6edc021ed91b6920ad1f4))
* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))
* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))
* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* record cosalette 0.9.3 framework baseline across remaining apps ([#248](https://github.com/ff-fab/cosalette-apps/issues/248)) ([3d32433](https://github.com/ff-fab/cosalette-apps/commit/3d324332d61320e0439d24383dbf18235b2b6dd5))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))
* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))
* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))
* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))
* upgrade to cosalette 0.12.0 ([e544dfc](https://github.com/ff-fab/cosalette-apps/commit/e544dfc0b30891432a623b0cbfcc39ccf380100d))
* **velux2mqtt:** stop shipping phantom HA-discovery entity ([#201](https://github.com/ff-fab/cosalette-apps/issues/201)) ([733e954](https://github.com/ff-fab/cosalette-apps/commit/733e95430bdfc5f3cb4c7f7c2a8ee40b144b7161))


### Documentation

* add zoomable docs images ([#92](https://github.com/ff-fab/cosalette-apps/issues/92)) ([0b14b99](https://github.com/ff-fab/cosalette-apps/commit/0b14b9975b1504fb52e2af1819d1de8ebf0ac9c9))
* **caldates2mqtt:** complete Epic 4  documentation, ADR, and deployment ([#69](https://github.com/ff-fab/cosalette-apps/issues/69)) ([5000630](https://github.com/ff-fab/cosalette-apps/commit/50006306def223b63af880bff75f69ed2ce71368))
* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* update cosalette badge with custom icon and fix click-zoom assets ([faa3724](https://github.com/ff-fab/cosalette-apps/commit/faa37245bd384edb3579b42433bac4b387de4fd5))
* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))
</details>

<details><summary>suncast: 0.4.0</summary>

## [0.4.0](https://github.com/ff-fab/cosalette-apps/compare/suncast-v0.3.0...suncast-v0.4.0) (2026-10-12)


###   BREAKING CHANGES

* error topic payloads follow cosalette 0.12.0 (ADR-091). A timed-out handler (`error_type` `timeout`) now publishes the message `TimeoutError` instead of an empty or library-provided message, and `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored unless the app opts in (only wiz2mqtt and wallpanel-control do). Check this release's app-specific notes for further operator actions.
* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error  it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))
* allow verbose error opt-in fleet-wide and settle cosalette 0.12.0 error disclosure (cap-mzz4) ([#402](https://github.com/ff-fab/cosalette-apps/issues/402)) ([1af9f8b](https://github.com/ff-fab/cosalette-apps/commit/1af9f8b7998810a84f5c5398f986891e852eba4e))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration  contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))
* **gas2mqtt:** add telemetry retry + review interval timeouts ([#170](https://github.com/ff-fab/cosalette-apps/issues/170)) ([420abcc](https://github.com/ff-fab/cosalette-apps/commit/420abcccd1aeb2a40927329e1529455722aad3bb))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* **jeelink2mqtt,suncast,velux2mqtt:** opt in to MQTT 5 retained-message expiry ([#283](https://github.com/ff-fab/cosalette-apps/issues/283)) ([d28e035](https://github.com/ff-fab/cosalette-apps/commit/d28e035b3a36cd3f8ff66b9b251e979ba7dcfca2))
* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* **suncast:** add clean-room shadow projection module ([#76](https://github.com/ff-fab/cosalette-apps/issues/76)) ([e168957](https://github.com/ff-fab/cosalette-apps/commit/e1689570e1c4f69b179116c92e8869f441ab2a0d))
* **suncast:** add configurable marker style and northeast building ([#84](https://github.com/ff-fab/cosalette-apps/issues/84)) ([7f110e5](https://github.com/ff-fab/cosalette-apps/commit/7f110e54185dd37727d3b3b4309590d7820785a8))
* **suncast:** add image delivery and output modules ([af69648](https://github.com/ff-fab/cosalette-apps/commit/af6964804760e53cbbba1605dde9cc41b0b383f5))
* **suncast:** add solar position computation module ([#74](https://github.com/ff-fab/cosalette-apps/issues/74)) ([7dfa94d](https://github.com/ff-fab/cosalette-apps/commit/7dfa94d084ed52830792ac17542f5a34c4a2e134))
* **suncast:** add sunny-side outline and sundial ring ([#83](https://github.com/ff-fab/cosalette-apps/issues/83)) ([3fae2a6](https://github.com/ff-fab/cosalette-apps/commit/3fae2a6527fd77abe0641c762bcd67fd26018452))
* **suncast:** add SVG geometry importer with sidecar support ([#77](https://github.com/ff-fab/cosalette-apps/issues/77)) ([56d1a86](https://github.com/ff-fab/cosalette-apps/commit/56d1a862f9114d01660d49531f409be2eff8df2a))
* **suncast:** add SVG shadow visualization renderer ([#78](https://github.com/ff-fab/cosalette-apps/issues/78)) ([06dfcbb](https://github.com/ff-fab/cosalette-apps/commit/06dfcbbb5e4110e52897269596f9330bd8288fe4))
* **suncast:** add YAML/JSON geometry loader with validation ([#75](https://github.com/ff-fab/cosalette-apps/issues/75)) ([ec5c89e](https://github.com/ff-fab/cosalette-apps/commit/ec5c89e6499d4fc5c883831ef427ea4918f96bad))
* **suncast:** adopt native health probe ([#347](https://github.com/ff-fab/cosalette-apps/issues/347)) ([a32a9e2](https://github.com/ff-fab/cosalette-apps/commit/a32a9e23e1341217f7c7568f68dadda54155035f))
* **suncast:** redesign sundial modes with compact dial ([#96](https://github.com/ff-fab/cosalette-apps/issues/96)) ([ea641dc](https://github.com/ff-fab/cosalette-apps/commit/ea641dc326075a6daba1ac3f8513903459ccdc57))
* **suncast:** rewrite shadow algorithm and fix renderer ([#82](https://github.com/ff-fab/cosalette-apps/issues/82)) ([18f6bbd](https://github.com/ff-fab/cosalette-apps/commit/18f6bbdbe0715cc14188d984f5e8d44f06aaa14f))
* **suncast:** scaffold app structure and ADRs ([#72](https://github.com/ff-fab/cosalette-apps/issues/72)) ([7eadbf4](https://github.com/ff-fab/cosalette-apps/commit/7eadbf4a737407b5a79d299319b151a74082932e))
* **suncast:** wire cosalette app with full telemetry pipeline ([#81](https://github.com/ff-fab/cosalette-apps/issues/81)) ([ad946aa](https://github.com/ff-fab/cosalette-apps/commit/ad946aa5afeb64d63e7580a69368de3e736fb171))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))
* **wallpanel-control:** implement adapters and test fixtures ([f337856](https://github.com/ff-fab/cosalette-apps/commit/f3378569fe7eba58107f17d407657da3c65eb54c))


### Bug Fixes

* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))
* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))
* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* record cosalette 0.9.3 framework baseline across remaining apps ([#248](https://github.com/ff-fab/cosalette-apps/issues/248)) ([3d32433](https://github.com/ff-fab/cosalette-apps/commit/3d324332d61320e0439d24383dbf18235b2b6dd5))
* resolve cosalette 0.5.1 ephemeral-store warning for store-less apps ([#167](https://github.com/ff-fab/cosalette-apps/issues/167)) ([e67b97c](https://github.com/ff-fab/cosalette-apps/commit/e67b97c054e39a7c40802d573a5ac848fe6a0204))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))
* **suncast:** address SVG renderer review findings ([541fb34](https://github.com/ff-fab/cosalette-apps/commit/541fb341391c320deb11f82e1da9bdb8fce3edc0))
* **suncast:** offload output I/O and bound hung filesystem writes ([#359](https://github.com/ff-fab/cosalette-apps/issues/359)) ([8197eac](https://github.com/ff-fab/cosalette-apps/commit/8197eacaf965fa8916e4a3d0a6044ab90e35199d))
* **suncast:** parallel shadow projection, auto-scaling, edge thickness ([#85](https://github.com/ff-fab/cosalette-apps/issues/85)) ([885943c](https://github.com/ff-fab/cosalette-apps/commit/885943c9b9b82620284aef08ef3aabd34c28ab0d))
* **suncast:** run PNG rasterization and file writes off the event loop ([#358](https://github.com/ff-fab/cosalette-apps/issues/358)) ([aae989d](https://github.com/ff-fab/cosalette-apps/commit/aae989dc52cd2d2a81ff368301e26b756611b37a))
* **taskfiles:** ignore GPL header in per-app similarity gate (cap-9dr) ([#185](https://github.com/ff-fab/cosalette-apps/issues/185)) ([dab2396](https://github.com/ff-fab/cosalette-apps/commit/dab2396e998a7fce2cd8d0b26cabe86adb59559c))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))
* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))
* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))
* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))
* upgrade to cosalette 0.12.0 ([e544dfc](https://github.com/ff-fab/cosalette-apps/commit/e544dfc0b30891432a623b0cbfcc39ccf380100d))


### Documentation

* add zoomable docs images ([#92](https://github.com/ff-fab/cosalette-apps/issues/92)) ([0b14b99](https://github.com/ff-fab/cosalette-apps/commit/0b14b9975b1504fb52e2af1819d1de8ebf0ac9c9))
* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* **suncast:** add .env.example, README with showcase images ([#86](https://github.com/ff-fab/cosalette-apps/issues/86)) ([77903ca](https://github.com/ff-fab/cosalette-apps/commit/77903ca60c976de663b82246fde26e57dd28470a))
* **suncast:** create documentation site ([#88](https://github.com/ff-fab/cosalette-apps/issues/88)) ([b96eccc](https://github.com/ff-fab/cosalette-apps/commit/b96eccc70187fc5ec1c9d53e61e7b07da951db9e))
* **suncast:** remove extra showcase image ([#91](https://github.com/ff-fab/cosalette-apps/issues/91)) ([8fac9de](https://github.com/ff-fab/cosalette-apps/commit/8fac9dec7c3d3263b1b92315c09fc136ab7029cb))
* update cosalette badge with custom icon and fix click-zoom assets ([faa3724](https://github.com/ff-fab/cosalette-apps/commit/faa37245bd384edb3579b42433bac4b387de4fd5))
* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))
</details>

<details><summary>wallpanel-control: 0.5.0</summary>

## [0.5.0](https://github.com/ff-fab/cosalette-apps/compare/wallpanel-control-v0.4.0...wallpanel-control-v0.5.0) (2026-10-12)


###   BREAKING CHANGES

* error topic payloads follow cosalette 0.12.0 (ADR-091). A timed-out handler (`error_type` `timeout`) now publishes the message `TimeoutError` instead of an empty or library-provided message, and `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored unless the app opts in (only wiz2mqtt and wallpanel-control do). Check this release's app-specific notes for further operator actions.
* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error  it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.
* **wallpanel:** refactor MQTT API

### Features

* add unavailable_on to command handlers ([#171](https://github.com/ff-fab/cosalette-apps/issues/171)) ([b6142b3](https://github.com/ff-fab/cosalette-apps/commit/b6142b338355505fad2ec63c7f32e16038cb43c1))
* adopt App.discovery() runtime HA discovery across apps ([8ccd74d](https://github.com/ff-fab/cosalette-apps/commit/8ccd74d87509b32e5238d9b9e55d263e25ba609a))
* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))
* allow verbose error opt-in fleet-wide and settle cosalette 0.12.0 error disclosure (cap-mzz4) ([#402](https://github.com/ff-fab/cosalette-apps/issues/402)) ([1af9f8b](https://github.com/ff-fab/cosalette-apps/commit/1af9f8b7998810a84f5c5398f986891e852eba4e))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration  contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* HA discovery schema enrichment for wallpanel-control + vito2mqtt (cap-3bz Phase 2) ([#181](https://github.com/ff-fab/cosalette-apps/issues/181)) ([34abe9c](https://github.com/ff-fab/cosalette-apps/commit/34abe9cf36dc879296bb189597d91aae17a52805))
* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))
* **vito2mqtt,wallpanel-control,wiz2mqtt:** opt in to MQTT 5 retained-message expiry ([#284](https://github.com/ff-fab/cosalette-apps/issues/284)) ([be74719](https://github.com/ff-fab/cosalette-apps/commit/be7471967ef5310a254782fc61026a8d3a3ade48))
* **wallpanel-control:** adopt native health probe ([#343](https://github.com/ff-fab/cosalette-apps/issues/343)) ([2238135](https://github.com/ff-fab/cosalette-apps/commit/223813583d7e0efd6c684f973e267ae2f8091946))
* **wallpanel-control:** define port protocols and settings ([ce620d4](https://github.com/ff-fab/cosalette-apps/commit/ce620d46c29d47f340a3d5deb1808c20d124a868))
* **wallpanel-control:** define port protocols and settings ([1eb3d18](https://github.com/ff-fab/cosalette-apps/commit/1eb3d18de0078389c65abc2b86ffa42c897de790))
* **wallpanel-control:** implement adapters and shared test fixtures ([436dc03](https://github.com/ff-fab/cosalette-apps/commit/436dc03d437b50b5f05c51eeb1c1107a98e83477))
* **wallpanel-control:** implement adapters and test fixtures ([f337856](https://github.com/ff-fab/cosalette-apps/commit/f3378569fe7eba58107f17d407657da3c65eb54c))
* **wallpanel-control:** one composite HA light for the display (cap-c9v) + ADR-input schema validation (cap-ak7) ([#254](https://github.com/ff-fab/cosalette-apps/issues/254)) ([0a73556](https://github.com/ff-fab/cosalette-apps/commit/0a7355693f578384e76f47a6382b90d582b39851))
* **wallpanel-control:** panel reachability probe and observed sleep/wake confirmation ([#398](https://github.com/ff-fab/cosalette-apps/issues/398)) ([fb57de8](https://github.com/ff-fab/cosalette-apps/commit/fb57de8b4bca685ebbbc10138ca7f72311ed3c27))
* **wallpanel-control:** re-publish last state at startup under MQTT 5 expiry ([#291](https://github.com/ff-fab/cosalette-apps/issues/291)) ([0e29185](https://github.com/ff-fab/cosalette-apps/commit/0e29185a347203bb20b7e0783e885d330d820316))
* **wallpanel-control:** scaffold app directory structure ([c619459](https://github.com/ff-fab/cosalette-apps/commit/c619459e2578ee5a970fe4baf873420ab60be69c))
* **wallpanel:** add control devices ([#135](https://github.com/ff-fab/cosalette-apps/issues/135)) ([eb719eb](https://github.com/ff-fab/cosalette-apps/commit/eb719ebdc0d1fa9b787a6dbe9bdd270b8c7f4be9))
* **wallpanel:** finish migration ([#137](https://github.com/ff-fab/cosalette-apps/issues/137)) ([c50fff9](https://github.com/ff-fab/cosalette-apps/commit/c50fff96dce3d8230255dab55284c682e09e1cfc))
* **wallpanel:** refactor MQTT API ([66582a2](https://github.com/ff-fab/cosalette-apps/commit/66582a29e834b55a672049aacb427fa5deca8e5c))


### Bug Fixes

* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))
* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))
* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* record cosalette 0.9.3 framework baseline across remaining apps ([#248](https://github.com/ff-fab/cosalette-apps/issues/248)) ([3d32433](https://github.com/ff-fab/cosalette-apps/commit/3d324332d61320e0439d24383dbf18235b2b6dd5))
* resolve cosalette 0.5.1 ephemeral-store warning for store-less apps ([#167](https://github.com/ff-fab/cosalette-apps/issues/167)) ([e67b97c](https://github.com/ff-fab/cosalette-apps/commit/e67b97c054e39a7c40802d573a5ac848fe6a0204))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))
* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))
* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))
* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))
* upgrade to cosalette 0.12.0 ([e544dfc](https://github.com/ff-fab/cosalette-apps/commit/e544dfc0b30891432a623b0cbfcc39ccf380100d))
* **wallpanel-control:** acknowledge repeated sleep while one is pending ([#386](https://github.com/ff-fab/cosalette-apps/issues/386)) ([01b8f0b](https://github.com/ff-fab/cosalette-apps/commit/01b8f0be314c2defd060f2a7f54043eca75767fb))
* **wallpanel-control:** add doc stubs and fix mosquitto config ([9c89e36](https://github.com/ff-fab/cosalette-apps/commit/9c89e3677c79064d129bb37a84aecf759e0e1552))
* **wallpanel-control:** harden SSH adapter and remove vendored assets ([9c4a21b](https://github.com/ff-fab/cosalette-apps/commit/9c4a21b4ab93c21cf3ae4c499a68c2d87c5dd1e7))
* **wallpanel-control:** use host networking so Wake-on-LAN reaches the LAN ([#388](https://github.com/ff-fab/cosalette-apps/issues/388)) ([3a373bf](https://github.com/ff-fab/cosalette-apps/commit/3a373bf0e7d0767b72d4314f5e412bcc5ab7e926))
* **wallpanel-control:** validation error type, quiet asyncssh logs, SSH keepalive ([#392](https://github.com/ff-fab/cosalette-apps/issues/392)) ([714b7e6](https://github.com/ff-fab/cosalette-apps/commit/714b7e6debeb25a0b9ae0e6a1a9b70297d84346d))


### Documentation

* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* update cosalette badge with custom icon and fix click-zoom assets ([faa3724](https://github.com/ff-fab/cosalette-apps/commit/faa37245bd384edb3579b42433bac4b387de4fd5))
* **wallpanel-control:** accept 45s probe latency ([#397](https://github.com/ff-fab/cosalette-apps/issues/397)) ([300bdd2](https://github.com/ff-fab/cosalette-apps/commit/300bdd260d394e69ddf6b4f5ca118a627f65c3a4))
* **wallpanel-control:** ADR for the reachability probe and sleep/wake confirmation ([#396](https://github.com/ff-fab/cosalette-apps/issues/396)) ([8379d13](https://github.com/ff-fab/cosalette-apps/commit/8379d135c05804f2e6916b7fee7c4561bc48782e))
* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))
</details>

<details><summary>wiz2mqtt: 0.4.0</summary>

## [0.4.0](https://github.com/ff-fab/cosalette-apps/compare/wiz2mqtt-v0.3.0...wiz2mqtt-v0.4.0) (2026-10-12)


###   BREAKING CHANGES

* error topic payloads follow cosalette 0.12.0 (ADR-091). A timed-out handler (`error_type` `timeout`) now publishes the message `TimeoutError` instead of an empty or library-provided message, and `<PREFIX>_MQTT__ERROR_PUBLISH_VERBOSE` is ignored unless the app opts in (only wiz2mqtt and wallpanel-control do). Check this release's app-specific notes for further operator actions.
* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error  it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))
* allow verbose error opt-in fleet-wide and settle cosalette 0.12.0 error disclosure (cap-mzz4) ([#402](https://github.com/ff-fab/cosalette-apps/issues/402)) ([1af9f8b](https://github.com/ff-fab/cosalette-apps/commit/1af9f8b7998810a84f5c5398f986891e852eba4e))
* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))
* **vito2mqtt,wallpanel-control,wiz2mqtt:** opt in to MQTT 5 retained-message expiry ([#284](https://github.com/ff-fab/cosalette-apps/issues/284)) ([be74719](https://github.com/ff-fab/cosalette-apps/commit/be7471967ef5310a254782fc61026a8d3a3ade48))
* **wiz2mqtt:** add discover CLI for LAN bulb onboarding (cap-10u.15) ([#240](https://github.com/ff-fab/cosalette-apps/issues/240)) ([a8e0d1b](https://github.com/ff-fab/cosalette-apps/commit/a8e0d1bd8d000801aedcb9db64242728bb6929fd))
* **wiz2mqtt:** add power-source settings and fake adapter test controls ([#276](https://github.com/ff-fab/cosalette-apps/issues/276)) ([75bc3ee](https://github.com/ff-fab/cosalette-apps/commit/75bc3eea0fe8c9e8b941e9e55cd2709456a61358))
* **wiz2mqtt:** add switched-relay boot safeguards ([#308](https://github.com/ff-fab/cosalette-apps/issues/308)) ([3912e05](https://github.com/ff-fab/cosalette-apps/commit/3912e059c8f4d084201ac56cb46e3cd88180b65a))
* **wiz2mqtt:** adopt native health probe ([#346](https://github.com/ff-fab/cosalette-apps/issues/346)) ([ce3625a](https://github.com/ff-fab/cosalette-apps/commit/ce3625a83242d61103fc363fed60d8088ca73a5c))
* **wiz2mqtt:** boot signal, desired state, command queue, power belief ([#278](https://github.com/ff-fab/cosalette-apps/issues/278)) ([7f8abe1](https://github.com/ff-fab/cosalette-apps/commit/7f8abe1f8ad4071523f902b4efbf0938cb2be5c9))
* **wiz2mqtt:** canonical hue/saturation colour model ([#218](https://github.com/ff-fab/cosalette-apps/issues/218)) ([c37aff6](https://github.com/ff-fab/cosalette-apps/commit/c37aff61ea2d5055cffe9681dbf39ec2a2adf81b))
* **wiz2mqtt:** clear stale openHAB colour, effect and power Items to NULL ([#389](https://github.com/ff-fab/cosalette-apps/issues/389)) ([e4f9996](https://github.com/ff-fab/cosalette-apps/commit/e4f999666c53f45080a8791577f4f0059dfa0605))
* **wiz2mqtt:** command handling  partial updates and mutual exclusion ([9cf174c](https://github.com/ff-fab/cosalette-apps/commit/9cf174c7396d38000cd79295aa51dfbc0851e74f))
* **wiz2mqtt:** consumer integration  runtime HA discovery and openHAB generation ([#238](https://github.com/ff-fab/cosalette-apps/issues/238)) ([36589bf](https://github.com/ff-fab/cosalette-apps/commit/36589bf3854b89138d730d167f9dfa818ceca8d9))
* **wiz2mqtt:** expose queued-command readiness state ([#307](https://github.com/ff-fab/cosalette-apps/issues/307)) ([17dd7e3](https://github.com/ff-fab/cosalette-apps/commit/17dd7e31439803c9efeee7dd851400cee7d6a95f))
* **wiz2mqtt:** full openHAB channels, power-request contract, OFF fixes ([#306](https://github.com/ff-fab/cosalette-apps/issues/306)) ([64ece03](https://github.com/ff-fab/cosalette-apps/commit/64ece03bac3cf121c95ec9932ce8799ff76a7807))
* **wiz2mqtt:** generate consumer bulb groups ([#243](https://github.com/ff-fab/cosalette-apps/issues/243)) ([ea4de28](https://github.com/ff-fab/cosalette-apps/commit/ea4de28e028d7e0acf4dfc18e37826741d97f59d))
* **wiz2mqtt:** generate openHAB power source items and per-bulb powered ([#296](https://github.com/ff-fab/cosalette-apps/issues/296)) ([1887436](https://github.com/ff-fab/cosalette-apps/commit/1887436ebccc2ac58e6e80f4be96d8a479541af0))
* **wiz2mqtt:** pace restore retries and confirm every colour restore ([#312](https://github.com/ff-fab/cosalette-apps/issues/312)) ([70c578a](https://github.com/ff-fab/cosalette-apps/commit/70c578a84273513e578963c58f18855e1b1fd6d6))
* **wiz2mqtt:** per-bulb capability-filtered HA discovery (cap-3tr) ([#241](https://github.com/ff-fab/cosalette-apps/issues/241)) ([3bbb122](https://github.com/ff-fab/cosalette-apps/commit/3bbb1227581e028dc1d07fe869b4ca51853833bc))
* **wiz2mqtt:** publish retained power requests per source ([#295](https://github.com/ff-fab/cosalette-apps/issues/295)) ([613883f](https://github.com/ff-fab/cosalette-apps/commit/613883fdcb6c1211d25a82e26ddabd3ea2c2a440))
* **wiz2mqtt:** restore desired state on return to reachability ([#279](https://github.com/ff-fab/cosalette-apps/issues/279)) ([31498f5](https://github.com/ff-fab/cosalette-apps/commit/31498f5423404f80a766c2c20d98e74ebbf5413b))
* **wiz2mqtt:** scaffold the app ([#213](https://github.com/ff-fab/cosalette-apps/issues/213)) ([6c374c6](https://github.com/ff-fab/cosalette-apps/commit/6c374c6a0d9b837438db88aa1d9bfe37533f8058))
* **wiz2mqtt:** settings and TOML bulb inventory ([#217](https://github.com/ff-fab/cosalette-apps/issues/217)) ([30b9836](https://github.com/ff-fab/cosalette-apps/commit/30b98361df67bf68cf18bd6bf93238cda64a4cc8))
* **wiz2mqtt:** ship host networking for WiZ push (cap-10u.16) ([#239](https://github.com/ff-fab/cosalette-apps/issues/239)) ([5a3c87b](https://github.com/ff-fab/cosalette-apps/commit/5a3c87b37b676d0cea4ff23bb551f0385b6d208d))
* **wiz2mqtt:** skip reads on a known-off power source, announce it in HA discovery ([#280](https://github.com/ff-fab/cosalette-apps/issues/280)) ([41d0366](https://github.com/ff-fab/cosalette-apps/commit/41d0366280feda56173efb7125dee13e7920326d))
* **wiz2mqtt:** state publication and availability debounce ([661f317](https://github.com/ff-fab/cosalette-apps/commit/661f3179bc383f0058a84d038edab00541dfd07b))
* **wiz2mqtt:** subscribe to power-source signals with cosalette inbound (closes cap-pnjx) ([#286](https://github.com/ff-fab/cosalette-apps/issues/286)) ([cf07555](https://github.com/ff-fab/cosalette-apps/commit/cf0755568be10a2572115361e2e0e676f3bb449e))
* **wiz2mqtt:** WizBulbPort adapter  push, state cache, capability detection ([#216](https://github.com/ff-fab/cosalette-apps/issues/216)) ([3ecc23d](https://github.com/ff-fab/cosalette-apps/commit/3ecc23d1e29941adf2b90cf5012cf74f4ac15b31))


### Bug Fixes

* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* **build:** scaffold-app.sh anchor/schema gaps and wiz2mqtt env wiring ([#214](https://github.com/ff-fab/cosalette-apps/issues/214)) ([6bf27f6](https://github.com/ff-fab/cosalette-apps/commit/6bf27f60d1e2023e4e4b174f1a85a45cea5e3161))
* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.2 across the workspace ([#288](https://github.com/ff-fab/cosalette-apps/issues/288)) ([f40153d](https://github.com/ff-fab/cosalette-apps/commit/f40153d26633c6b4fdc9b704a002169dcceebbf8))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))
* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))
* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))
* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))
* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))
* upgrade cosalette to 0.11.4 ([#370](https://github.com/ff-fab/cosalette-apps/issues/370)) ([ff99ff6](https://github.com/ff-fab/cosalette-apps/commit/ff99ff6ab0de0265a72fd51b1c55b2066d17914d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))
* upgrade to cosalette 0.12.0 ([e544dfc](https://github.com/ff-fab/cosalette-apps/commit/e544dfc0b30891432a623b0cbfcc39ccf380100d))
* **wiz2mqtt:** clear superseded colour mode on optimistic state merge ([#270](https://github.com/ff-fab/cosalette-apps/issues/270)) ([3eb5c64](https://github.com/ff-fab/cosalette-apps/commit/3eb5c6437ab51924e753e885e113a44543239f2f))
* **wiz2mqtt:** diagnose and retry a failed push registration ([#273](https://github.com/ff-fab/cosalette-apps/issues/273)) ([e4e4c69](https://github.com/ff-fab/cosalette-apps/commit/e4e4c690b4ca2dcb82adff6a65eb3b5e0f8fcd29))
* **wiz2mqtt:** harden bulb first contact ([#269](https://github.com/ff-fab/cosalette-apps/issues/269)) ([62c3d2d](https://github.com/ff-fab/cosalette-apps/commit/62c3d2de303918c5090953f3ed1bb7abe8ea956f))
* **wiz2mqtt:** harden power and HSB commands ([#311](https://github.com/ff-fab/cosalette-apps/issues/311)) ([c136d42](https://github.com/ff-fab/cosalette-apps/commit/c136d42f5da614ca5872fb7480a097e59a947306))
* **wiz2mqtt:** probe with the bulb's own clock so the heartbeat liveness check is real ([#272](https://github.com/ff-fab/cosalette-apps/issues/272)) ([60d2d14](https://github.com/ff-fab/cosalette-apps/commit/60d2d144547c079f7a2c46247116d18b72be385b))
* **wiz2mqtt:** reconnect observability, direct commands during reconnect, image smoke tests ([#372](https://github.com/ff-fab/cosalette-apps/issues/372)) ([7f07c4d](https://github.com/ff-fab/cosalette-apps/commit/7f07c4da829445bc66d83a7f8e352da3d256a0fe))
* **wiz2mqtt:** restore a quick power cycle that missed no poll ([#371](https://github.com/ff-fab/cosalette-apps/issues/371)) ([f237418](https://github.com/ff-fab/cosalette-apps/commit/f23741825bb67deebbe252642cc70ef221848f22))
* **wiz2mqtt:** restore white/CT-mode state and stop reverting user commands ([#367](https://github.com/ff-fab/cosalette-apps/issues/367)) ([665b9eb](https://github.com/ff-fab/cosalette-apps/commit/665b9eb4f3be147976be62933f419f1a95a59239))
* **wiz2mqtt:** round fractional numbers on the .../set command fields ([#299](https://github.com/ff-fab/cosalette-apps/issues/299)) ([019cb55](https://github.com/ff-fab/cosalette-apps/commit/019cb55e4cb2a40f633acbcebc1d7acf62e76621))
* **wiz2mqtt:** set WIZ2MQTT_STORE_PATH so the capability cache survives recreation ([#271](https://github.com/ff-fab/cosalette-apps/issues/271)) ([2a6defa](https://github.com/ff-fab/cosalette-apps/commit/2a6defa61b135ce12e79fea9ddcaa3638f9cf82a))
* **wiz2mqtt:** ship PyYAML so wiz2mqtt-openhab works in the image ([#364](https://github.com/ff-fab/cosalette-apps/issues/364)) ([0110984](https://github.com/ff-fab/cosalette-apps/commit/0110984ca794551e170fb2db954ad7385dd172f1))
* **wiz2mqtt:** stabilize return-path restore ([#309](https://github.com/ff-fab/cosalette-apps/issues/309)) ([c798d7d](https://github.com/ff-fab/cosalette-apps/commit/c798d7d0d172bb0c339ba6dfb16c064df2dde8b2))
* **wiz2mqtt:** stop duplicate firstBeat re-arming after an adopt-only return ([#377](https://github.com/ff-fab/cosalette-apps/issues/377)) ([9221472](https://github.com/ff-fab/cosalette-apps/commit/9221472ecec964f372d3c9f949f9f2b558f051c0))
* **wiz2mqtt:** stop spurious firstBeat restores and replay one colour mode ([#368](https://github.com/ff-fab/cosalette-apps/issues/368)) ([f7b6e5b](https://github.com/ff-fab/cosalette-apps/commit/f7b6e5b696b5ebb797d776f3cd0711c2b613bbb5))
* **wiz2mqtt:** stop the powered flap after a relay signal off ([#373](https://github.com/ff-fab/cosalette-apps/issues/373)) ([5630c00](https://github.com/ff-fab/cosalette-apps/commit/5630c0085f43d7e03bdb85ee7c4f3672665d0ca4))
* **wiz2mqtt:** turn the belief off at once on a relay signal 'off' ([#298](https://github.com/ff-fab/cosalette-apps/issues/298)) ([3912f43](https://github.com/ff-fab/cosalette-apps/commit/3912f43c9ebcd033b6a476c14dd27e0b4fa73c93))


### Documentation

* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))
* **wiz2mqtt:** document mains power awareness for operators and consumers ([#297](https://github.com/ff-fab/cosalette-apps/issues/297)) ([f10db18](https://github.com/ff-fab/cosalette-apps/commit/f10db18cc01452c9295570f47331eff32223afcf))
* **wiz2mqtt:** fix cross-site ADR link and document publication behaviour ([#226](https://github.com/ff-fab/cosalette-apps/issues/226)) ([5b3f2e6](https://github.com/ff-fab/cosalette-apps/commit/5b3f2e6c76d7a4821c12329926610c40408586d5))
* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))
* **wiz2mqtt:** record mains power awareness ADRs and plan the epic ([#267](https://github.com/ff-fab/cosalette-apps/issues/267)) ([dd0d842](https://github.com/ff-fab/cosalette-apps/commit/dd0d84285114e80ec460d58ff62c6eb3a3cc5c13))
</details>

---
This PR was generated with [Release Please](https://github.com/googleapis/release-please). See [documentation](https://github.com/googleapis/release-please#release-please).