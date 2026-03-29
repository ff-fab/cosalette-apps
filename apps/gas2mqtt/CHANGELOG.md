# Changelog

## [0.1.2](https://github.com/ff-fab/cosalette-apps/compare/gas2mqtt-v0.1.1...gas2mqtt-v0.1.2) (2026-03-29)


### Features

* **docs:** add header breadcrumb linking app docs to monorepo root ([b488fca](https://github.com/ff-fab/cosalette-apps/commit/b488fca7cd11738c2187c2d2f87437c42efd6168))
* **docs:** add mkdocs-click-zoom plugin to all documentation sites ([#70](https://github.com/ff-fab/cosalette-apps/issues/70)) ([cba3f9a](https://github.com/ff-fab/cosalette-apps/commit/cba3f9a57192fbad2bad6d7d7ca0a0b1692cb031))
* **docs:** add per-app version display to docs sites ([#34](https://github.com/ff-fab/cosalette-apps/issues/34)) ([4cde5e1](https://github.com/ff-fab/cosalette-apps/commit/4cde5e1c1a8d1bd81a093ba0ec3eceded61969d4))
* **docs:** shared doc assets + header breadcrumb for app sites ([f05aed3](https://github.com/ff-fab/cosalette-apps/commit/f05aed3fd0b954929186ea8f0412bd58e8033635))
* **docs:** sync light/dark palette across all documentation sites ([#42](https://github.com/ff-fab/cosalette-apps/issues/42)) ([1806c9f](https://github.com/ff-fab/cosalette-apps/commit/1806c9fdfdcb2b5b8c52c34ce4ee795d0f0f7f21))
* **velux2mqtt:** add calibration state machine ([#46](https://github.com/ff-fab/cosalette-apps/issues/46)) ([ae5dad1](https://github.com/ff-fab/cosalette-apps/commit/ae5dad1f416f76c72db565c2572c110c42e29ae9))


### Bug Fixes

* address PR review — restore thread-safety and loop resilience ([a31a7c5](https://github.com/ff-fab/cosalette-apps/commit/a31a7c5a8915926b4e9adcd62c709f7b87e01b33))
* **docs:** replace symlinks with pre-build copy for shared assets ([6e80a76](https://github.com/ff-fab/cosalette-apps/commit/6e80a76b4fc5a1ad202314b0f32a3527546713bf))
* **docs:** replace symlinks with pre-build copy for shared assets ([#40](https://github.com/ff-fab/cosalette-apps/issues/40)) ([bafb4d1](https://github.com/ff-fab/cosalette-apps/commit/bafb4d17d048880ad6d69b76ff50c67c219653da))
* **gas2mqtt:** remove error-swallowing in gas counter device ([1c79cb9](https://github.com/ff-fab/cosalette-apps/commit/1c79cb9f8215a1a9ab3c3aca483186a5d1398fc6))
* remove error-swallowing in device handlers ([9f4ed14](https://github.com/ff-fab/cosalette-apps/commit/9f4ed147752c7a2e710cda84977bd98ecafe1091))

## [0.1.1](https://github.com/ff-fab/cosalette-apps/compare/gas2mqtt-v0.1.0...gas2mqtt-v0.1.1) (2026-03-21)


### Features

* **gas2mqtt:** migrate gas2mqtt into monorepo ([#2](https://github.com/ff-fab/cosalette-apps/issues/2)) ([55b6b00](https://github.com/ff-fab/cosalette-apps/commit/55b6b000b1e504927c9c780d265a12f243bd5beb))
* **gas2mqtt:** migrate gas2mqtt into monorepo (Phase 2) ([#5](https://github.com/ff-fab/cosalette-apps/issues/5)) ([cef92a4](https://github.com/ff-fab/cosalette-apps/commit/cef92a4c83190d7fee2612e25cb8a2013b1e7be3))
* **jeelink2mqtt:** migrate jeelink2mqtt into monorepo ([#6](https://github.com/ff-fab/cosalette-apps/issues/6)) ([b3992d6](https://github.com/ff-fab/cosalette-apps/commit/b3992d648da10735b5d4eafcf1b969f619834b93))


### Bug Fixes

* **gas2mqtt:** replace *** with --- in docs grid cards ([dd9fb2c](https://github.com/ff-fab/cosalette-apps/commit/dd9fb2cd2320453c3823864499bdeeccc9a5ee8b))
* release-please CI gate and gas2mqtt release ([#27](https://github.com/ff-fab/cosalette-apps/issues/27)) ([2ea1d32](https://github.com/ff-fab/cosalette-apps/commit/2ea1d32b215a2465a235ad2d4198ec58d2e3a64a))


### Documentation

* fix gas2mqtt tiles and polish monorepo root docs ([82fd520](https://github.com/ff-fab/cosalette-apps/commit/82fd520f18b42874d088c8a2fd6f694dd53e385e))

## [0.1.1](https://github.com/ff-fab/cosalette-apps/compare/gas2mqtt-v0.1.0...gas2mqtt-v0.1.1) (2026-03-20)


### Features

* **gas2mqtt:** migrate gas2mqtt into monorepo ([#2](https://github.com/ff-fab/cosalette-apps/issues/2)) ([55b6b00](https://github.com/ff-fab/cosalette-apps/commit/55b6b000b1e504927c9c780d265a12f243bd5beb))
* **gas2mqtt:** migrate gas2mqtt into monorepo (Phase 2) ([#5](https://github.com/ff-fab/cosalette-apps/issues/5)) ([cef92a4](https://github.com/ff-fab/cosalette-apps/commit/cef92a4c83190d7fee2612e25cb8a2013b1e7be3))
* **jeelink2mqtt:** migrate jeelink2mqtt into monorepo ([#6](https://github.com/ff-fab/cosalette-apps/issues/6)) ([b3992d6](https://github.com/ff-fab/cosalette-apps/commit/b3992d648da10735b5d4eafcf1b969f619834b93))

## [0.1.5](https://github.com/ff-fab/gas2mqtt/compare/v0.1.4...v0.1.5) (2026-03-14)


### Features

* adopt edge tag convention, rename container workflow ([#23](https://github.com/ff-fab/gas2mqtt/issues/23)) ([bab848e](https://github.com/ff-fab/gas2mqtt/commit/bab848ef7a215fb758ccdf6ece405f8d7673423d))
* two-job release workflow, Alpine image, inline compose docs ([#19](https://github.com/ff-fab/gas2mqtt/issues/19)) ([f367db8](https://github.com/ff-fab/gas2mqtt/commit/f367db8bf3063bd050ff8ec9daa71a4d52b2a839))


### Bug Fixes

* copy README.md into Docker build context ([#21](https://github.com/ff-fab/gas2mqtt/issues/21)) ([f0984b2](https://github.com/ff-fab/gas2mqtt/commit/f0984b2de8e625e7898daba29de7de9f219407b7))

## [0.1.4](https://github.com/ff-fab/gas2mqtt/compare/v0.1.3...v0.1.4) (2026-03-14)


### Bug Fixes

* build container inline in release-please workflow ([#17](https://github.com/ff-fab/gas2mqtt/issues/17)) ([d098da4](https://github.com/ff-fab/gas2mqtt/commit/d098da43e3b580c0533f49ff0275c755a16f765e))

## [0.1.3](https://github.com/ff-fab/gas2mqtt/compare/v0.1.2...v0.1.3) (2026-03-14)


### Bug Fixes

* trigger container build on tag push, not release event ([#15](https://github.com/ff-fab/gas2mqtt/issues/15)) ([1ae6e88](https://github.com/ff-fab/gas2mqtt/commit/1ae6e88d61fee0d05db30b50d6a3e43c554a4afe))

## [0.1.2](https://github.com/ff-fab/gas2mqtt/compare/v0.1.1...v0.1.2) (2026-03-14)


### Bug Fixes

* add latest tag fallback for workflow_dispatch ([#13](https://github.com/ff-fab/gas2mqtt/issues/13)) ([ee3467f](https://github.com/ff-fab/gas2mqtt/commit/ee3467fd1717735f72eb0778ecfa716a6f52f219))

## [0.1.1](https://github.com/ff-fab/gas2mqtt/compare/v0.1.0...v0.1.1) (2026-03-14)


### Features

* :sparkles: add issues.jsonl file ([a1d33bf](https://github.com/ff-fab/gas2mqtt/commit/a1d33bf560d429aa1abd06c2716c8150f7134c04))
* :sparkles: initial commit ([bd38e21](https://github.com/ff-fab/gas2mqtt/commit/bd38e217926975ebfab7322b7c0f82b4320a27bb))
* adopt cosalette 0.1.2 publish strategies ([#6](https://github.com/ff-fab/gas2mqtt/issues/6)) ([f9e7722](https://github.com/ff-fab/gas2mqtt/commit/f9e7722ea08a22c78c358d4c21313c82513af366))
* adopt cosalette 0.1.4 — PT1 filter, init=, eager settings ([#8](https://github.com/ff-fab/gas2mqtt/issues/8)) ([a723da9](https://github.com/ff-fab/gas2mqtt/commit/a723da976deefab3341b23f828cd4f345e49e5a4))
* adopt cosalette 0.1.5 — declarative main.py ([#9](https://github.com/ff-fab/gas2mqtt/issues/9)) ([f14b6fd](https://github.com/ff-fab/gas2mqtt/commit/f14b6fdb2b8d6ae4b517128f7b237cabcf513776))
* migrate gas2mqtt to cosalette framework ([8175256](https://github.com/ff-fab/gas2mqtt/commit/8175256847d949a420af0c2d5975bb56c2d12c78))
* publish app image to GHCR on release ([#12](https://github.com/ff-fab/gas2mqtt/issues/12)) ([c516595](https://github.com/ff-fab/gas2mqtt/commit/c51659566f032ce4ff0426eba30b030019fc4ada))
* state persistence for gas counter ([#5](https://github.com/ff-fab/gas2mqtt/issues/5)) ([153535f](https://github.com/ff-fab/gas2mqtt/commit/153535f1f6404d729ee707ca17290cacf510e19a))


### Bug Fixes

* :bug: update import path for ClassUnderTest in test file template ([2fa2be5](https://github.com/ff-fab/gas2mqtt/commit/2fa2be562f256a0c5ddf44d270833de3f8b8f894))
* use settings injection for storage adapter and document registration-time limits ([#7](https://github.com/ff-fab/gas2mqtt/issues/7)) ([bf2163c](https://github.com/ff-fab/gas2mqtt/commit/bf2163c64788f6a985e2648ba3491d008fa214d5))
