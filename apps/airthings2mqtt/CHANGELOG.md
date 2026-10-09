# Changelog

## Unreleased

### Bug Fixes

* honor `AIRTHINGS2MQTT_DEVICE_NAME` for state, set, error, and availability topics, correcting routing for non-default device names
* check BlueZ adapter power over the system D-Bus for bounded, read-only operational health reporting instead of probing for `/sys/class/bluetooth/hci0`

## [0.3.2](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.3.1...airthings2mqtt-v0.3.2) (2026-10-09)


### Features

* **airthings2mqtt:** adopt native health probe ([#348](https://github.com/ff-fab/cosalette-apps/issues/348)) ([dff6285](https://github.com/ff-fab/cosalette-apps/commit/dff62856b272fcf3e8e5b4ee86a1fdc77f5c18b9))
* ship app images without rich (ADR-013) ([#351](https://github.com/ff-fab/cosalette-apps/issues/351)) ([5194d12](https://github.com/ff-fab/cosalette-apps/commit/5194d1259738b59773935c79e3fe8bb7ce155cc1))


### Bug Fixes

* **airthings2mqtt:** drop the bluez package from the image ([#354](https://github.com/ff-fab/cosalette-apps/issues/354)) ([d941a7c](https://github.com/ff-fab/cosalette-apps/commit/d941a7cf2c22b4798da340fa2a79ba9e490d66af))
* answer --help/--version from every app and keep uv.lock out of images ([#353](https://github.com/ff-fab/cosalette-apps/issues/353)) ([087f40c](https://github.com/ff-fab/cosalette-apps/commit/087f40c4b49bbf595ee5821febb06d9d76ef056a))
* **deps:** drop cosalette[schema] and redundant TYPER_USE_RICH from app images ([#357](https://github.com/ff-fab/cosalette-apps/issues/357)) ([b7558cc](https://github.com/ff-fab/cosalette-apps/commit/b7558cc861b6b2db54a5cb0490037249b23abd17))
* **deps:** upgrade apps to cosalette 0.11.1 ([#332](https://github.com/ff-fab/cosalette-apps/issues/332)) ([2fa3d29](https://github.com/ff-fab/cosalette-apps/commit/2fa3d2945e410ac2f83d8d23ae1b4165719aa890))
* **deps:** upgrade apps to cosalette 0.11.2 ([3a3110f](https://github.com/ff-fab/cosalette-apps/commit/3a3110f0b59bf69c51e1a2edaef91150d72896ee))
* **deps:** upgrade apps to cosalette 0.11.2 ([47b4ba3](https://github.com/ff-fab/cosalette-apps/commit/47b4ba34de3842905b3e7d646999650d7c378d50))
* **deps:** upgrade apps to cosalette 0.11.3 ([#352](https://github.com/ff-fab/cosalette-apps/issues/352)) ([cac690d](https://github.com/ff-fab/cosalette-apps/commit/cac690d4af332b967338a917506ba721efa8d394))
* slim app images (no uv/pip) and fix airthings2mqtt store path ([#330](https://github.com/ff-fab/cosalette-apps/issues/330)) ([7eb86a5](https://github.com/ff-fab/cosalette-apps/commit/7eb86a50df96cca138986b54570f6a0de857a439))

## [0.3.1](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.3.0...airthings2mqtt-v0.3.1) (2026-10-04)


### Features

* drop Docker HEALTHCHECK, MQTT is the health signal (ADR-010) ([#328](https://github.com/ff-fab/cosalette-apps/issues/328)) ([13d3cd8](https://github.com/ff-fab/cosalette-apps/commit/13d3cd8b278286079c39c3c5e4a4bdf73546e2c6))


### Bug Fixes

* compile Python bytecode in app images ([e09cefd](https://github.com/ff-fab/cosalette-apps/commit/e09cefdc4979f4818d19216a985446e294a75e9a))

## [0.3.0](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.2.7...airthings2mqtt-v0.3.0) (2026-10-04)


### ⚠ BREAKING CHANGES

* **airthings2mqtt:** the host needs a system account for UID 10001, because dbus-daemon refuses connections from a UID without a host account, and existing data volumes or bind mounts must be chowned to 10001:10001. See docs/host-setup.md.

### Features

* **airthings2mqtt:** add last_read and rssi to the state payload ([#321](https://github.com/ff-fab/cosalette-apps/issues/321)) ([d68a664](https://github.com/ff-fab/cosalette-apps/commit/d68a66479415c17cf0c975bcb3ceaace4f768c8b))
* **airthings2mqtt:** add pre-connect advertiser scan ([dc8e103](https://github.com/ff-fab/cosalette-apps/commit/dc8e103c7c1bd685cb71ddebd230dc03d445c1b7))
* **airthings2mqtt:** cosalette 0.11 freshness, health check, dedicated UID and host D-Bus hardening ([#323](https://github.com/ff-fab/cosalette-apps/issues/323)) ([8ecaafb](https://github.com/ff-fab/cosalette-apps/commit/8ecaafbc1755729bcb42e551089ec2c33c100efa))
* **airthings2mqtt:** detect sensor reset, withhold radon placeholders, publish measurement_state ([#324](https://github.com/ff-fab/cosalette-apps/issues/324)) ([e6ebfab](https://github.com/ff-fab/cosalette-apps/commit/e6ebfabdb013ef490fe98708496e1fed834b0ea1))


### Bug Fixes

* **airthings2mqtt:** declare BLE reader not restartable; ADR-003 no adapter power-cycling ([#322](https://github.com/ff-fab/cosalette-apps/issues/322)) ([1eedda3](https://github.com/ff-fab/cosalette-apps/commit/1eedda3434e338000c20d5866be27f7ccef2bd46))
* **airthings2mqtt:** retry and redact BLE device-not-found failures (early-adopter feedback) ([#316](https://github.com/ff-fab/cosalette-apps/issues/316)) ([b97fce1](https://github.com/ff-fab/cosalette-apps/commit/b97fce1d1ee7aff26b2babf904c39571828bdd94))
* **deps:** upgrade apps to cosalette 0.11.0 ([#319](https://github.com/ff-fab/cosalette-apps/issues/319)) ([2c35f5d](https://github.com/ff-fab/cosalette-apps/commit/2c35f5dc366abeae84f6ed9f2d11e27755ab4be3))

## [0.2.7](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.2.6...airthings2mqtt-v0.2.7) (2026-10-02)


### Bug Fixes

* **deps:** upgrade apps to cosalette 0.10.6 ([#315](https://github.com/ff-fab/cosalette-apps/issues/315)) ([f45aa69](https://github.com/ff-fab/cosalette-apps/commit/f45aa69ef2ded1de6a94f3a06618325755596769))

## [0.2.6](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.2.5...airthings2mqtt-v0.2.6) (2026-09-30)


### Bug Fixes

* upgrade cosalette to 0.10.5 and compose wiz queue ([#303](https://github.com/ff-fab/cosalette-apps/issues/303)) ([4323d8e](https://github.com/ff-fab/cosalette-apps/commit/4323d8eb9d73cb76e11c8db1dc62bcd0c1d829bb))

## [0.2.5](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.2.4...airthings2mqtt-v0.2.5) (2026-09-28)


### Bug Fixes

* upgrade cosalette to 0.10.4 ([#301](https://github.com/ff-fab/cosalette-apps/issues/301)) ([f92482f](https://github.com/ff-fab/cosalette-apps/commit/f92482fe755b820601d5505f89e404c6cba27907))

## [0.2.4](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.2.3...airthings2mqtt-v0.2.4) (2026-09-19)


### Features

* **airthings2mqtt,caldates2mqtt,gas2mqtt:** opt in to MQTT 5 retained-message expiry ([#282](https://github.com/ff-fab/cosalette-apps/issues/282)) ([d3e07da](https://github.com/ff-fab/cosalette-apps/commit/d3e07da88145058433b0f88fc5a40a87a1b3ceb0))


### Bug Fixes

* **deps:** adopt cosalette 0.10.2 across the workspace ([#287](https://github.com/ff-fab/cosalette-apps/issues/287)) ([6f86628](https://github.com/ff-fab/cosalette-apps/commit/6f8662889b1a1218c6a0f1041b007f41deb45b7a))
* **deps:** adopt cosalette 0.10.3 across the workspace ([#292](https://github.com/ff-fab/cosalette-apps/issues/292)) ([6e31553](https://github.com/ff-fab/cosalette-apps/commit/6e315530510650e6f1ffbc4e02ec552ce4d262ee))
* **deps:** resolve and validate cosalette 0.10.1 across the workspace ([#277](https://github.com/ff-fab/cosalette-apps/issues/277)) ([9968187](https://github.com/ff-fab/cosalette-apps/commit/996818747a41699d8221bb7bd34dec2c568beb2e))

## [0.2.3](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.2.2...airthings2mqtt-v0.2.3) (2026-09-13)


### Features

* adopt cosalette 0.10 ([#265](https://github.com/ff-fab/cosalette-apps/issues/265)) ([678dcb4](https://github.com/ff-fab/cosalette-apps/commit/678dcb482cf51daa7ceea6f4cfe8efe5b81cb18b))

## [0.2.2](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.2.1...airthings2mqtt-v0.2.2) (2026-09-12)


### Bug Fixes

* **docs:** publish app docs from root updates ([#264](https://github.com/ff-fab/cosalette-apps/issues/264)) ([0188712](https://github.com/ff-fab/cosalette-apps/commit/0188712a1b300624d502571f6828064adf3ceb0d))
* upgrade cosalette to 0.9.4 and declare per-channel discovery intent ([#250](https://github.com/ff-fab/cosalette-apps/issues/250)) ([632b58b](https://github.com/ff-fab/cosalette-apps/commit/632b58b612c8c46d83aa78ad8ac51a74039ad79e))
* upgrade cosalette to 0.9.5 and plan the migration work it unlocks ([#252](https://github.com/ff-fab/cosalette-apps/issues/252)) ([0103c59](https://github.com/ff-fab/cosalette-apps/commit/0103c5955b817a1ab468fe28880400f6debd2d6a))
* upgrade cosalette to 0.9.6 ([#256](https://github.com/ff-fab/cosalette-apps/issues/256)) ([965ef69](https://github.com/ff-fab/cosalette-apps/commit/965ef691d5e810f3790c3c9eb7145c49955ba43d))


### Documentation

* **wiz2mqtt:** record cap-10u.19 hardware verification findings ([#262](https://github.com/ff-fab/cosalette-apps/issues/262)) ([d3ca03e](https://github.com/ff-fab/cosalette-apps/commit/d3ca03ea6064260dee4804bfa08a8cadce212550))

## [0.2.1](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.2.0...airthings2mqtt-v0.2.1) (2026-09-08)


### Bug Fixes

* record cosalette 0.9.3 framework baseline across remaining apps ([#248](https://github.com/ff-fab/cosalette-apps/issues/248)) ([3d32433](https://github.com/ff-fab/cosalette-apps/commit/3d324332d61320e0439d24383dbf18235b2b6dd5))

## [0.2.0](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.1.5...airthings2mqtt-v0.2.0) (2026-09-05)


### ⚠ BREAKING CHANGES

* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error — it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* adopt App.discovery() runtime HA discovery across apps ([8ccd74d](https://github.com/ff-fab/cosalette-apps/commit/8ccd74d87509b32e5238d9b9e55d263e25ba609a))
* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))


### Documentation

* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))

## [0.1.5](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.1.4...airthings2mqtt-v0.1.5) (2026-08-09)


### Features

* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))


### Bug Fixes

* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))

## [0.1.4](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.1.3...airthings2mqtt-v0.1.4) (2026-06-27)


### Bug Fixes

* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))

## [0.1.3](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.1.2...airthings2mqtt-v0.1.3) (2026-06-27)


### Bug Fixes

* **airthings2mqtt:** redact BLE MAC in log + make health_check async ([#144](https://github.com/ff-fab/cosalette-apps/issues/144)) ([ed5b027](https://github.com/ff-fab/cosalette-apps/commit/ed5b0278bb6b1ecf0b1c8d7c51ab2ca6c5ce2034))

## [0.1.2](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.1.1...airthings2mqtt-v0.1.2) (2026-06-25)


### Features

* add adapter resilience ([60547a7](https://github.com/ff-fab/cosalette-apps/commit/60547a7c52b298f4c425be5437e7f66b02499a4e))
* **airthings2mqtt:** support triggerable rereads ([#129](https://github.com/ff-fab/cosalette-apps/issues/129)) ([e56f907](https://github.com/ff-fab/cosalette-apps/commit/e56f9075f443e5ddc05e98f20316b0b4c53554bc))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration — contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))
* **wallpanel-control:** implement adapters and test fixtures ([f337856](https://github.com/ff-fab/cosalette-apps/commit/f3378569fe7eba58107f17d407657da3c65eb54c))


### Documentation

* add zoomable docs images ([#92](https://github.com/ff-fab/cosalette-apps/issues/92)) ([0b14b99](https://github.com/ff-fab/cosalette-apps/commit/0b14b9975b1504fb52e2af1819d1de8ebf0ac9c9))
* update cosalette badge with custom icon and fix click-zoom assets ([faa3724](https://github.com/ff-fab/cosalette-apps/commit/faa37245bd384edb3579b42433bac4b387de4fd5))

## [0.1.1](https://github.com/ff-fab/cosalette-apps/compare/airthings2mqtt-v0.1.0...airthings2mqtt-v0.1.1) (2026-03-28)


### Features

* **airthings2mqtt:** scaffold app with settings, BLE adapters, and tests ([#59](https://github.com/ff-fab/cosalette-apps/issues/59)) ([d57daeb](https://github.com/ff-fab/cosalette-apps/commit/d57daebe85aa0dd03f4bc90fd9912d06171f7137))
* **airthings2mqtt:** telemetry device handler with full test coverage ([#61](https://github.com/ff-fab/cosalette-apps/issues/61)) ([e828adf](https://github.com/ff-fab/cosalette-apps/commit/e828adf602ba858e75b0978638b9b5f039e28408))
* **docs:** add mkdocs-click-zoom plugin to all documentation sites ([#70](https://github.com/ff-fab/cosalette-apps/issues/70)) ([cba3f9a](https://github.com/ff-fab/cosalette-apps/commit/cba3f9a57192fbad2bad6d7d7ca0a0b1692cb031))


### Documentation

* **airthings2mqtt:** add documentation and deployment config ([#62](https://github.com/ff-fab/cosalette-apps/issues/62)) ([7ab869a](https://github.com/ff-fab/cosalette-apps/commit/7ab869a5bff963339613e9fdf98ea1ff630317c2))
* homogenise app documentation with top-bar nav and rich homepages ([#63](https://github.com/ff-fab/cosalette-apps/issues/63)) ([beaf450](https://github.com/ff-fab/cosalette-apps/commit/beaf4506166fae75dc542c68ce124260b2cd967f))

## Changelog
