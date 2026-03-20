# Changelog

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
