# Changelog

## [0.1.1](https://github.com/ff-fab/cosalette-apps/compare/vito2mqtt-v0.1.0...vito2mqtt-v0.1.1) (2026-03-21)


### Features

* add Docker deployment infrastructure ([#19](https://github.com/ff-fab/cosalette-apps/issues/19)) ([accb046](https://github.com/ff-fab/cosalette-apps/commit/accb046566aab643583bca35d0e219ab6ea318ef))
* implement adapter layer (ports & adapters) ([#6](https://github.com/ff-fab/cosalette-apps/issues/6)) ([50b1697](https://github.com/ff-fab/cosalette-apps/commit/50b1697d41c9cce2625096bfd8d4d383f7f37986))
* implement command handlers for writable parameters ([#11](https://github.com/ff-fab/cosalette-apps/issues/11)) ([a658c69](https://github.com/ff-fab/cosalette-apps/commit/a658c69c28f9fb8c09259f090e922e4eb820dc68))
* implement Optolink P300 protocol layer ([#5](https://github.com/ff-fab/cosalette-apps/issues/5)) ([cfe3417](https://github.com/ff-fab/cosalette-apps/commit/cfe34179aa0cf7cb07141fc9dee81d580c85cfa4))
* implement telemetry devices (all 7 signal groups) ([#9](https://github.com/ff-fab/cosalette-apps/issues/9)) ([301f09b](https://github.com/ff-fab/cosalette-apps/commit/301f09baf37b5c821ea19d09415291fe7ab9c2ad))
* integrate coalescing groups for telemetry handlers ([e43c7d2](https://github.com/ff-fab/cosalette-apps/commit/e43c7d20742afa66ce222234886a674a122f2cd4))
* integrate coalescing groups for telemetry handlers ([1d94e5a](https://github.com/ff-fab/cosalette-apps/commit/1d94e5aafef5e82f387625a96d9d9523d288fce4))
* legionella treatment feature ([#15](https://github.com/ff-fab/cosalette-apps/issues/15)) ([3a57e8b](https://github.com/ff-fab/cosalette-apps/commit/3a57e8b445fe3ac77ddc010b2a9d8ca96ad1bdf6))
* make store path configurable via VITO2MQTT_STORE_PATH ([#22](https://github.com/ff-fab/cosalette-apps/issues/22)) ([c54c9ee](https://github.com/ff-fab/cosalette-apps/commit/c54c9eeb14a3303db38c1da5bdf19aadb6121f7d))
* read-before-write optimization for command handlers ([#13](https://github.com/ff-fab/cosalette-apps/issues/13)) ([21b2ef8](https://github.com/ff-fab/cosalette-apps/commit/21b2ef8a28e3e0d01c92b6259f5c748f4bf9b7c6))
* **vito2mqtt:** migrate vito2mqtt into monorepo ([a88dde1](https://github.com/ff-fab/cosalette-apps/commit/a88dde1e059a45fb421a4e15cefd32276c7d6eae))
* **vito2mqtt:** migrate vito2mqtt into monorepo ([f5afe32](https://github.com/ff-fab/cosalette-apps/commit/f5afe32076088fe6d899277efb88f2c83728957d))
* wire app composition root with CLI entry point ([#12](https://github.com/ff-fab/cosalette-apps/issues/12)) ([7aecc81](https://github.com/ff-fab/cosalette-apps/commit/7aecc816b97f7ceda37e0c016e31ac572554fcc9))


### Bug Fixes

* allow --help/--version without env vars ([#14](https://github.com/ff-fab/cosalette-apps/issues/14)) ([a2867e8](https://github.com/ff-fab/cosalette-apps/commit/a2867e81562a2e8d130b5a0b31cf5b9deaba5f98))
* delegate Dolt server lifecycle to bd dolt start ([#8](https://github.com/ff-fab/cosalette-apps/issues/8)) ([118f8ba](https://github.com/ff-fab/cosalette-apps/commit/118f8ba8ae43796a962ada89006a40b81ae00bd0))
* **vito2mqtt:** align Dockerfile with monorepo pattern and fix doc payloads ([80e593d](https://github.com/ff-fab/cosalette-apps/commit/80e593d223d3d385bd6ea20065da8df2c1517c5a))


### Reverts

* undo direct commits to main (use PR instead) ([a385bd1](https://github.com/ff-fab/cosalette-apps/commit/a385bd1bc61460bcc82598e66062794059ebad0a))


### Documentation

* add 5 foundational ADRs for vito2mqtt architecture ([4d60e14](https://github.com/ff-fab/cosalette-apps/commit/4d60e1424fc7d70777ae4364e05959d3bd1abe18))
* add 5 foundational ADRs for vito2mqtt architecture ([75ba017](https://github.com/ff-fab/cosalette-apps/commit/75ba0174a872a628a23eec1ac8ffd0c488ea2995))
* add ADR-006 configurable signal language (DE/EN) ([d64b297](https://github.com/ff-fab/cosalette-apps/commit/d64b297a4d97938254e4591974faeb67cc7ceeb6))
* add ADR-006 configurable signal language (DE/EN) ([9d8b9a2](https://github.com/ff-fab/cosalette-apps/commit/9d8b9a21b933e37e10bfb0f8478a4442d7ee6bb6))
* add ADR-007 coalescing groups and framework requirements ([fa9d59f](https://github.com/ff-fab/cosalette-apps/commit/fa9d59fbc842dde0341fa0023fc59d6b4850e38a))
* add complete documentation site ([#16](https://github.com/ff-fab/cosalette-apps/issues/16)) ([57bd640](https://github.com/ff-fab/cosalette-apps/commit/57bd6407a69506f42af1551cbbd20dbab8cf628a))
* address PR review comments ([dc18fcd](https://github.com/ff-fab/cosalette-apps/commit/dc18fcddcc349904eabb57be530f2d33fdff326f))
* fix mode count, error count, and pipe rendering in ADR-006 ([dc8aa3f](https://github.com/ff-fab/cosalette-apps/commit/dc8aa3f3853bfb8667e0cb14a14c8714a7c6dc83))
* refine context section in ADR-006 for clarity ([9da4f95](https://github.com/ff-fab/cosalette-apps/commit/9da4f95adbfce31cfb9115ee0fc833cc7dfd34bf))

## [0.1.2](https://github.com/ff-fab/vito2mqtt/compare/v0.1.1...v0.1.2) (2026-03-06)


### Features

* add Docker deployment infrastructure ([#19](https://github.com/ff-fab/vito2mqtt/issues/19)) ([76eafc0](https://github.com/ff-fab/vito2mqtt/commit/76eafc0c9ea9cb3a5756a1a619a5911f89016aed))
* make store path configurable via VITO2MQTT_STORE_PATH ([#22](https://github.com/ff-fab/vito2mqtt/issues/22)) ([bb296c2](https://github.com/ff-fab/vito2mqtt/commit/bb296c23bf397303eebd83a7ba1a13bc9342fa00))


### Reverts

* undo direct commits to main (use PR instead) ([36d02a7](https://github.com/ff-fab/vito2mqtt/commit/36d02a7e74c8f3c8ce2d7fe3a53e45fb704e7c8d))

## [0.1.1](https://github.com/ff-fab/vito2mqtt/compare/v0.1.0...v0.1.1) (2026-03-05)


### Features

* implement adapter layer (ports & adapters) ([#6](https://github.com/ff-fab/vito2mqtt/issues/6)) ([e2ae282](https://github.com/ff-fab/vito2mqtt/commit/e2ae28277ef189c92932360e2bac7a4dd115e393))
* implement command handlers for writable parameters ([#11](https://github.com/ff-fab/vito2mqtt/issues/11)) ([d4f614b](https://github.com/ff-fab/vito2mqtt/commit/d4f614bb2b076fa06514e54e9c2358a7bafee008))
* implement Optolink P300 protocol layer ([#5](https://github.com/ff-fab/vito2mqtt/issues/5)) ([efde886](https://github.com/ff-fab/vito2mqtt/commit/efde886c5f9f4f20489ed2a885e6701e2dfcd7ac))
* implement telemetry devices (all 7 signal groups) ([#9](https://github.com/ff-fab/vito2mqtt/issues/9)) ([68aa90a](https://github.com/ff-fab/vito2mqtt/commit/68aa90a12dee74d655de0af1684fb74889a555da))
* integrate coalescing groups for telemetry handlers ([abdacb3](https://github.com/ff-fab/vito2mqtt/commit/abdacb3413a6d6922799760470fdb8f968874642))
* integrate coalescing groups for telemetry handlers ([0740bbb](https://github.com/ff-fab/vito2mqtt/commit/0740bbb4ffaedbd1a402398c22dc1de1812d5ffd))
* legionella treatment feature ([#15](https://github.com/ff-fab/vito2mqtt/issues/15)) ([ed819a0](https://github.com/ff-fab/vito2mqtt/commit/ed819a0c642561c87fdf621a8036c3b15034b6d4))
* read-before-write optimization for command handlers ([#13](https://github.com/ff-fab/vito2mqtt/issues/13)) ([abf4204](https://github.com/ff-fab/vito2mqtt/commit/abf4204c60b9e807977fd709c837e5ead4bdc031))
* wire app composition root with CLI entry point ([#12](https://github.com/ff-fab/vito2mqtt/issues/12)) ([bef2321](https://github.com/ff-fab/vito2mqtt/commit/bef23218dc23ec344f795e55a439f22e294d4654))


### Bug Fixes

* allow --help/--version without env vars ([#14](https://github.com/ff-fab/vito2mqtt/issues/14)) ([860ac57](https://github.com/ff-fab/vito2mqtt/commit/860ac57594874fa58d6a7489b199c6f9f4547d33))
* delegate Dolt server lifecycle to bd dolt start ([#8](https://github.com/ff-fab/vito2mqtt/issues/8)) ([fca69e8](https://github.com/ff-fab/vito2mqtt/commit/fca69e832c1598092a58178e075a1e2c0f665ef3))
