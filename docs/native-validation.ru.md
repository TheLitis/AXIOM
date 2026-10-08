# Доказательства нативной проверки

[English](native-validation.md) · [Работа адаптера и критерии](native-adapter.ru.md) · [Требования к конечной системе](end-goal-requirements.ru.md)

**Статус финальной проверки: native capture и input response наблюдаются; точное совпадение повторов НЕ ПРОШЛО.** Один observation baseline и три контролируемых реплея завершились. Доставленный ввод совпал, но callback flags, выбранные состояния игрока и terminal rotation не совпали точно. Smoke runner отклонил repeat gate с кодом 1. M1 остаётся открытым.

Эксперимент запускает локально сгенерированный classic-тест в настоящем Windows x64 движке Geometry Dash 2.2081 с Geode 5.8.2. Расписание ввода — специально подготовленные тестовые данные, а не человеческие результаты. Контролируемый реплей использует объявленную owned-input policy. Этот эксперимент не устанавливает эквивалентность обычному vanilla/человеческому вводу, полную детерминированность движка, измеренные timing windows или AR.

## Идентичность финальной сборки и запуска

| Доказательство | Финальное значение |
|---|---|
| Дата/время запуска и каталог доказательств | 2026-10-08 около 21:55 UTC / 2026-10-09 около 00:55 MSK; локальный `reports/native/smoke-2377b6ffa9ca434d9749e1f5f39ff257` |
| Записанный commit репозитория | `393ed19b8df3f8375a7023a37fde0a5ca57ea852` |
| Native source-tree SHA-256 | `c44ed6b7d0eed2cf10a7a367bc42405e5f6ffd62c18521007c6d2005e3a1fd41` |
| Конфигурация сборки, компилятор и build log | Release x64; Visual Studio 18 2026; MSVC 19.51.36256.0; Windows SDK 10.0.26100.0; локальный `reports/native-build.log` |
| SHA-256 пакета | `f8d37d484e026d353936c42c525675321fd42bfb3bbaf68546d4098bd9c2ad3f` |
| SHA-256 загруженного бинарника адаптера | `c00d43203744ab26dddb7ed1ad733f0e79c899376e784b8f5c2c9ea0cf7a1269` |
| Фактический game executable SHA-256 | `fc5a16c292278bc2e8e078fb1d5023c2bd658322dd72712767ea70c2dd9ec6d0` |
| Фактическая версия loader и SHA-256 бинарника | 5.8.2; `61847e05d4aa416bfd4d1f4e026b5b0e66848756473b285add6233a5cc9356d2` |
| SDK commit | `2a5fd87433da47d6bf07221774f0cbb25535ae08` |
| Bindings commit | `2a8b5c489ce8b49e7061b0543aa2bc5b22570063` |
| SHA-256 исходной строки тестового уровня | `af8167d7ab8240a2798840a5f479f3af6144647c7bb41423e2303492b0e05558` |
| Действующая input policy и input source | `process-commands-pre-hook-owned-input-v1`; baseline `unknown`, повторы `replay` |
| Environment SHA-256 | `48117ad99bf95b4b830ad53fde644ba469d397551c8fef5b0791ea002d8fd251` |
| Записанные загруженные моды | `axiom.native-capture` 0.1.0 и `geode.loader` 5.8.2; `configuration_complete: false` |
| Sandbox writable-path check | Runtime-журналы подтверждают `.tools/runtime/sandbox-saves`; loader update checks пропущены |
| Исходный loader / журнал личных сохранений | SHA-256 исходного установленного loader совпадает с неизменённым хешем 5.8.2 выше; полный before-after ledger личных сохранений **не собирался** |
| Runtime-журналы загрузки и экспорта | Локальные loader logs в 00:55:17, 00:55:25, 00:55:34 и 00:55:42 MSK; smoke log `reports/native-smoke.log` |
| Публичные доказательства | Curated-метрики и хеши в этом документе; исходные captures, comparison и logs остаются локальными ignored reports |

Source-tree digest обозначает native-файлы, CMake и manifest мода, вошедшие в сборку; один commit не обозначает незакоммиченные изменения. Пакет собран с SDK-предупреждениями MSB8027 о совпадающих именах object files; они сохранены в журнале. Нельзя объединять записи разных сборок, политик или сред, переписывая identity fields. Публичная JSON-проверка по-прежнему сообщает о неаутентифицированном происхождении и только выбранных полях.

Программные проверки прошли: 183 теста и 83 подслучая, Ruff, форматирование и сборка Python wheel/source. [Нативная сборка Windows](https://github.com/TheLitis/AXIOM/actions/runs/37850395564) и [Python CI на Windows/Linux 3.11/3.14](https://github.com/TheLitis/AXIOM/actions/runs/37850395573) прошли на commit `47c9eb56e0e77ff01cfeecc730a018713baeeafb`. Компиляция в CI не запускает игру и не аутентифицирует локальные записи движка.

| Сохранённый локальный артефакт | SHA-256 |
|---|---|
| `baseline.json` | `f0bb9e3797466cdc74161d89ee470aaff87be827cff26156c13af2a6e91c4452` |
| `replay-1.json` | `37ba856ea8fca23f0ebdbcc46429a40337e63a56cd3ea6d99ada39e9a95ca28f` |
| `replay-2.json` | `93f21c5a8d5d1d1c133fbbb7726f9d4e5b6eaa7e39e934ec296d1bd84321d3e8` |
| `replay-3.json` | `599367030823e4f0f3d629246f1436aaeb4c283d96120298815e6c4671e0eb55` |
| `replay.json` | `749d6ecb61eb53bd30d85bfbe5c23d91b58f08baec4869f1f7f39b228cfabef4` |
| `comparison.json` | `562cf9174c2a8caac47f58bfe6d6fe17af9587a18be0de5a11bde2866a7ef8ac` |

## Runtime-доказательства

Smoke-скрипт создал один observation baseline и три контролируемых повтора с нажатием player-1/button-1 на command index 60 и отпусканием на 90. Это индексы вызовов обработки команд, а не подтверждённые physics ticks или визуальные кадры. `baseline.json` — observation baseline; comparator повторов использует **`replay-1.json` как базу сравнения**.

| Проверка | Финальное наблюдение |
|---|---|
| Baseline: полный старт, observation source, native completion | `level_start`, `unknown`, `PlayLayer::levelComplete` на 734; 735 trace records |
| Попыток / экспортов / schema-valid replay repetitions | 3 / 3 / 3; каждый `level_start`, `replay` |
| Native outcome и terminal command index реплеев | Все три `completed` через `PlayLayer::levelComplete` на 733 |
| Исполнение запланированных запросов без хвоста | По 2 запроса; хвост 0 |
| Native player push/release callbacks | Push на 60 и release на 90, оба `native_return: true` во всех трёх реплеях |
| Trace / delivered-input / blocked-request counts | Каждый реплей: 734 / 4 / 1; baseline: 735 / 2 / 0 |
| Точное совпадение доставленного ввода и расписания | **PASS** во всех трёх реплеях, без wall diagnostics |
| Точное совпадение callback arguments | **FAIL**; первые отличающиеся вызовы 89 и 126 |
| Точное совпадение выбранных полей игрока | **FAIL**; первые отличающиеся вызовы 542 и 504 |
| Точное совпадение terminal callback/outcome/placement | **PASS** между реплеями |
| Точное совпадение отдельных terminal player fields | **FAIL**; отличается player-1 rotation |
| Совпадение blocked-request diagnostics | Одинаковая сигнатура: один player-1/button-1 release неизвестного происхождения на call 1; не определяет delivered-subset consistency |
| Итоговый comparison status | `recorded_subset_inconsistent` |
| Smoke exit и сохранённые артефакты | Код 1, repeat gate не пройден; все четыре captures, inspections, plan и comparison сохранены локально |

На call 61 все три реплея записали player-1 `y=107.46690368652344` и `y_velocity=10.964`; observation baseline записал `y=105` и velocity 0. Native callbacks и изменение траектории наблюдаются. Это сравнение не изолирует контрфактический эффект подавления других запросов. Одно завершение не устанавливает точность реплея, а native Boolean returns не устанавливают время аппаратного события или независимо проверенное принятие ввода.

## Известные расхождения и смысл результата

**Финальный результат: точное совпадение не прошло в обоих сравнениях с replay 1.** Расписание и сигнатуры доставленного ввода совпадают. Callback `dt` и half flags совпадают; отличается `is_last_tick`. Selected-state differences относятся к player-1 x/y/rotation. Допуски и фильтры полей не применялись.

| Пара | Callback differences | Отличия выбранных полей игрока | Terminal player-1 rotation |
|---|---|---|---|
| Replay 1 и 2 | Первый call 89; 4 отличия `is_last_tick` | Первый call 542; 192 отличающиеся записи; x/y/rotation отличаются в 192 записях каждый | 538.072998046875 и 538.2860717773438 |
| Replay 1 и 3 | Первый call 126; 3 отличия `is_last_tick` | Первый call 504; 230 отличающихся записей; y/rotation отличаются в 230 записях, x — в 226 начиная с 506 | 538.072998046875 и 538.1959228515625 |

Текущее правило точно сравнивает callback `dt`/half/last flags, порядок/фазы/returns доставленного ввода, выбранные поля игрока, расписание и отдельный terminal. Input wall timestamps и terminal wall duration — исключённая диагностика. Наблюдаемые различия flags и x/y/rotation остаются провалом точного сравнения. Их момент совместим с гипотезой влияния animation/batching, но эта причина **не доказана**: нужен изолирующий её контролируемый эксперимент.

Даже `recorded_subset_consistent` относится только к объявленным полям и проверенному тесту. Inconsistent означает незакрытый repeat-agreement gate, а не невозможность всех маршрутов или уровней. Owned-channel replay может подавлять engine-generated requests неизвестного происхождения. Прямые вызовы методов игрока и эквивалентность обычному вводу остаются за пределами доказанного.

## Локальное воспроизведение

Нужны законная локальная установка игры, поддерживаемый Windows x64 компилятор и PowerShell 5.1 или новее. Выполни из корня репозитория:

```powershell
uv sync --locked --extra dev
powershell -NoProfile -File .\scripts\build-native.ps1 -Jobs 4
powershell -NoProfile -File .\scripts\run-native-smoke.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -Repetitions 3
powershell -NoProfile -File .\scripts\run-native-controls.ps1 -GameDirectory 'C:\path\to\Geometry Dash'
```

Smoke runner готовит игнорируемую тестовую копию, отклоняет уже запущенный `AXIOMSandbox`, запускает собственный скрытый процесс и останавливает только его. Он временно записывает локальное расписание и затем восстанавливает прежний файл. Подготовка проверяет обычные test/save roots, фиксированный хеш игры и отсутствие staged loader update; изолированный loader profile отключает автоматическую проверку обновлений. Это не заменяет журнал личных сохранений до-после и не доказывает изоляцию всех save access paths.

Доказательства сохраняются в уникальном `reports/native/smoke-*`. Неудачная запись, отсутствие input response, несовместимое identity или inconsistent comparison являются ошибкой; каталог и runtime logs нужно сохранить. Сам `axiom native-compare` может вернуть нулевой код при inconsistent, поскольку сравнение сформировано успешно; smoke runner отдельно проверяет статус и отклоняет такой результат.

Независимая проверка сохранённых файлов; подставь настоящий каталог:

```powershell
.\.venv\Scripts\python.exe -m axiom native 'reports\native\smoke-ID\baseline.json'
.\.venv\Scripts\python.exe -m axiom native-compare 'reports\native\smoke-ID\replay-1.json' 'reports\native\smoke-ID\replay-2.json' 'reports\native\smoke-ID\replay-3.json' --json 'reports\native\smoke-ID\comparison-recheck.json'
```

Скопированные game binaries, игровые ресурсы и личные сохранения не публикуются. Репозиторий публикует curated-метрики, хеши, код генерации теста и команды воспроизведения; исходные captures/comparison/logs остаются в ignored local `reports/`. Отдельного публичного summary JSON нет. Опубликованный журнал позволяет выполнить независимый запуск, но не заменяет независимую аутентификацию исходных частных файлов.

## Нативные контрольные запуски

Controls использовали ту же adapter/loader/environment identity и сохранены локально в `reports/native/controls-8bbb4349d560475f9c19642834c01c01`. Controls runner завершился с кодом 0.

Опубликованный controls runner также успешно выполнен в PowerShell 7 и Windows PowerShell 5.1 с тем же бинарником и исходами. Локальные журналы — `reports/native-controls-public.log` и `reports/native-controls-ps5.log`; процессы завершены, replay/fixture files восстановлены.

| Control | Наблюдаемый результат |
|---|---|
| Сгенерированная опасность, level SHA-256 `f76afc3faf8bb328f668a2a2202600dfe17e46a9fc133f342a51dd337aeaace9` | `PlayLayer::destroyPlayer`, `died` на call 218; 219 trace records; player-1 dead, x=283.0182800292969, y=105; complete integrity, ошибок 0; inspector принял |
| Реплей с неверным level digest из нулей | `AXIOM::error` на call 0; одна trace record; `recording_complete: false`, ошибка `Replay level hash mismatch`; inspector отклонил с кодом 2 |

SHA-256 сохранённого `death.json` — `f0eafac416bb62cdc288b8c68fc4e8d2a4ce59344d42fcd149a3767b0ee58ca6`; `wrong-level.json` — `08aeb6db9493016e9d4a6e6584cfa3f78c08b7df27efe30a10490c787b57c74b`. Эти controls подтверждают один death path и один отказ неверной цели, а не полную native rejection/mechanics matrix.

## Негативные и непроверенные критерии

В финальных результатах нужно различать испытанный runtime-отказ, Python-only contract checks и полностью непроверенные механики. Успех unit test не устанавливает native pass.

| Критерий | Финальный статус / необходимые доказательства |
|---|---|
| Native capture, full-start completion и input response | **OBSERVED** для сгенерированного теста и объявленной политики |
| Точное совпадение повторов выбранного набора | **FAILED** в запуске трёх реплеев; M1 открыт |
| Отказ чужому level replay в игре | **OBSERVED** в одном control с нулевым target digest |
| Отказ чужому environment replay в игре | **NOT_TESTED** |
| Отказ другой build/loader/mod set и update drift | **NOT_ESTABLISHED** для полной runtime-матрицы |
| Native death control отдельно от completion | **OBSERVED** для одной сгенерированной опасности, callback и post-call trace одного запуска |
| Пауза, фокус, reset, quit и disable controls | **NOT_ESTABLISHED**; реальные callback paths и маркировка unknown starts |
| Подавление и диагностика неинжекторных запросов | **OBSERVED** для сохранённого запроса на call 1; происхождение unknown, без forwarding |
| Прямой обход через методы игрока и другие input/physics mods | **UNSUPPORTED / NOT_ESTABLISHED** |
| Другие classic modes, triggers, dual и матрица механик | **UNTESTED** вне объявленного теста |
| Platformer, другие версии игры и ОС | **UNSUPPORTED** в первой области |
| Recording overhead, throughput и scheduling resolution | **NOT_MEASURED** |
| Полная конфигурация и детерминированность всего движка | **NOT_ESTABLISHED** |
| Checkpoint restore/continuation equivalence | **NOT_IMPLEMENTED / NOT_ESTABLISHED** |
| Full-run native perturbation windows | **NOT_MEASURED** |
| Human telemetry, predictive calibration и настоящий level AR | **NOT_ESTABLISHED** |

Успешные capture/input/control observations не закрывают проваленный repeat gate и непроверенные критерии выше.
