# Changelog

## [0.2.0](https://github.com/ff-fab/cosalette-apps/compare/jeelink2mqtt-v0.1.4...jeelink2mqtt-v0.2.0) (2026-09-05)


### ⚠ BREAKING CHANGES

* state_model= now outranks the return annotation and validates every telemetry and command return (ADR-068). A handler declaring state_model=M alongside a differently typed annotation emits a UserWarning at registration, which filterwarnings=["error"] turns into a collection error — it broke five registrations here, covering ten entities. The loose "-> dict[str, object]" annotations are dropped so state_model= is the sole contract, per the upstream migration note: airthings _telemetry, caldates calendar, gas2mqtt gas_counter and temperature, and vito's telemetry handler factory for all seven Optolink signal groups.

### Features

* migrate to cosalette 0.6.1, close two of three wiz2mqtt gates ([#208](https://github.com/ff-fab/cosalette-apps/issues/208)) ([13b72e0](https://github.com/ff-fab/cosalette-apps/commit/13b72e06eaee774163e0c1d89371d140c17ce574))
* migrate to cosalette 0.6.3, close the final wiz2mqtt gate ([#210](https://github.com/ff-fab/cosalette-apps/issues/210)) ([30850af](https://github.com/ff-fab/cosalette-apps/commit/30850afb62cf2a3b906179d91a3f0c03d6868955))
* upgrade to cosalette 0.9.0 and adopt state_model enforcement ([#228](https://github.com/ff-fab/cosalette-apps/issues/228)) ([7a9c0ef](https://github.com/ff-fab/cosalette-apps/commit/7a9c0ef3e1079bb780d465147db579101630586c))


### Documentation

* fix ADR-006 link, scope airthings2mqtt device claim, document _meta/ topics ([#229](https://github.com/ff-fab/cosalette-apps/issues/229)) ([4c2f7af](https://github.com/ff-fab/cosalette-apps/commit/4c2f7af29c635d597f95c99f40cc61db95f80c64))

## [0.1.4](https://github.com/ff-fab/cosalette-apps/compare/jeelink2mqtt-v0.1.3...jeelink2mqtt-v0.1.4) (2026-08-09)


### Features

* upgrade cosalette to 0.5.7 and adopt HA-discovery + error-hardening features ([#182](https://github.com/ff-fab/cosalette-apps/issues/182)) ([f00edd0](https://github.com/ff-fab/cosalette-apps/commit/f00edd00267aaad6f14c6604bc51686ee5727124))


### Bug Fixes

* **cosalette:** bump to 0.5.10 for schema fail-loud + settings-resolve mode ([#202](https://github.com/ff-fab/cosalette-apps/issues/202)) ([3107afe](https://github.com/ff-fab/cosalette-apps/commit/3107afe237204d53a48c13d7ee106a2f81370ed4))
* **cosalette:** unicode schema fix + jeelink2mqtt HA-discovery decision ([#200](https://github.com/ff-fab/cosalette-apps/issues/200)) ([d81b76e](https://github.com/ff-fab/cosalette-apps/commit/d81b76e77b5a89b2eefda606d3c29142205eefdd))
* **deps:** upgrade cosalette to 0.6.0, resolve cap-wv9 schema-check asymmetry ([#204](https://github.com/ff-fab/cosalette-apps/issues/204)) ([2010b5e](https://github.com/ff-fab/cosalette-apps/commit/2010b5e44fe713c01acb73009916449ee580a36b))
* **taskfiles:** ignore GPL header in per-app similarity gate (cap-9dr) ([#185](https://github.com/ff-fab/cosalette-apps/issues/185)) ([dab2396](https://github.com/ff-fab/cosalette-apps/commit/dab2396e998a7fce2cd8d0b26cabe86adb59559c))

## [0.1.3](https://github.com/ff-fab/cosalette-apps/compare/jeelink2mqtt-v0.1.2...jeelink2mqtt-v0.1.3) (2026-06-27)


### Bug Fixes

* trigger releases for cosalette 0.4.5 upgrade across all apps ([#146](https://github.com/ff-fab/cosalette-apps/issues/146)) ([5e3100f](https://github.com/ff-fab/cosalette-apps/commit/5e3100f3b4e128955adb3fb93d7dc5a7c9c19768))

## [0.1.2](https://github.com/ff-fab/cosalette-apps/compare/jeelink2mqtt-v0.1.1...jeelink2mqtt-v0.1.2) (2026-06-26)


### Features

* add adapter resilience ([60547a7](https://github.com/ff-fab/cosalette-apps/commit/60547a7c52b298f4c425be5437e7f66b02499a4e))
* cosalette 0.3.11 adoption + compose.yml rename ([#112](https://github.com/ff-fab/cosalette-apps/issues/112)) ([234c23b](https://github.com/ff-fab/cosalette-apps/commit/234c23b8cc8dd098339ea134dbbf27fda479d1d2))
* cosalette 0.3.6 migration — contract metadata + gas2mqtt refactor ([#111](https://github.com/ff-fab/cosalette-apps/issues/111)) ([cc1932d](https://github.com/ff-fab/cosalette-apps/commit/cc1932d593cac7645dd7463a0c0f9daa7c3e6bdb))
* **docs:** add header breadcrumb linking app docs to monorepo root ([d62851d](https://github.com/ff-fab/cosalette-apps/commit/d62851db69839bd2830b629d5a72ef09cd9519c3))
* **docs:** add mkdocs-click-zoom plugin to all documentation sites ([#70](https://github.com/ff-fab/cosalette-apps/issues/70)) ([21c85ec](https://github.com/ff-fab/cosalette-apps/commit/21c85ece8667ba3a7a46d738c1c24847e985a8a9))
* **docs:** add per-app version display to docs sites ([#34](https://github.com/ff-fab/cosalette-apps/issues/34)) ([d355c0e](https://github.com/ff-fab/cosalette-apps/commit/d355c0e8dbe440af2bdcb0f242859a4f2ea02e3b))
* **docs:** shared doc assets + header breadcrumb for app sites ([4e57caf](https://github.com/ff-fab/cosalette-apps/commit/4e57caf09f8db1de4d891536c8f62905c9c10b29))
* **docs:** sync light/dark palette across all documentation sites ([#42](https://github.com/ff-fab/cosalette-apps/issues/42)) ([ad7daeb](https://github.com/ff-fab/cosalette-apps/commit/ad7daeb8e2ff1d02e29590ac33d6e4db33b332e4))
* **gas2mqtt:** modernize with cosalette 0.3.5 (FEP-001 + FEP-002) ([#110](https://github.com/ff-fab/cosalette-apps/issues/110)) ([93d1166](https://github.com/ff-fab/cosalette-apps/commit/93d1166b961e9ab44dbda5792880e13fdf1534d1))
* upgrade cosalette 0.4 and close cap-5xy ([#124](https://github.com/ff-fab/cosalette-apps/issues/124)) ([039e3ef](https://github.com/ff-fab/cosalette-apps/commit/039e3efa6c88f5122f366b4833ed799aa75056f1))
* upgrade to cosalette 0.4.4 and add AsyncAPI schema gate ([#141](https://github.com/ff-fab/cosalette-apps/issues/141)) ([679190e](https://github.com/ff-fab/cosalette-apps/commit/679190e7e66dd96f55bb360a3ea51dd4578424ee))


### Bug Fixes

* address PR review — restore thread-safety and loop resilience ([b9b3d41](https://github.com/ff-fab/cosalette-apps/commit/b9b3d4120bba307c223e18c9d1b2cac152819e6b))
* **docs:** replace symlinks with pre-build copy for shared assets ([a0b8243](https://github.com/ff-fab/cosalette-apps/commit/a0b82436d55f63f650892d7163d2ecc0b7400c73))
* **docs:** replace symlinks with pre-build copy for shared assets ([#40](https://github.com/ff-fab/cosalette-apps/issues/40)) ([483e35f](https://github.com/ff-fab/cosalette-apps/commit/483e35f40ee684e4726df38e2e9752e48a211160))
* **jeelink2mqtt:** remove error-swallowing in LaCrosse adapter ([e410a23](https://github.com/ff-fab/cosalette-apps/commit/e410a234fa2e063849f4dbb1cca7904429f22367))
* remove error-swallowing in device handlers ([ee46221](https://github.com/ff-fab/cosalette-apps/commit/ee46221a44c8ea4a0b060066a40dd3ef37bfc5e8))


### Documentation

* add zoomable docs images ([#92](https://github.com/ff-fab/cosalette-apps/issues/92)) ([0b14b99](https://github.com/ff-fab/cosalette-apps/commit/0b14b9975b1504fb52e2af1819d1de8ebf0ac9c9))

## [0.1.1](https://github.com/ff-fab/cosalette-apps/compare/jeelink2mqtt-v0.1.0...jeelink2mqtt-v0.1.1) (2026-03-21)


### Features

* **jeelink2mqtt:** migrate jeelink2mqtt into monorepo ([#6](https://github.com/ff-fab/cosalette-apps/issues/6)) ([b3992d6](https://github.com/ff-fab/cosalette-apps/commit/b3992d648da10735b5d4eafcf1b969f619834b93))
