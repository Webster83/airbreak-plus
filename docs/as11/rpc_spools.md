# AS11 RPC Spool Reference

This document lists every known `StartSpool` spool type, its payload
family, and the inner record shapes for each family. Protocol
mechanics, request fields, status codes, and the cursor-advance
caveat are described in
[AS11 RPC Protocol](rpc_protocol.md#spool-rpc).

## Contents

- [Spool registry](#spool-registry)
  - [Families](#families)
  - [Full enumeration](#full-enumeration)
- [Inner record shapes](#inner-record-shapes)
  - [Event records](#event-records)
  - [TherapyOneMinutePeriodic records](#therapyoneminuteperiodic-records)
  - [RC03 archived-signal records](#rc03-archived-signal-records)

## Spool registry

<!-- spool-registry: begin -->

### Families

| Family | Spool types | Notes |
|--------|-------------|-------|
| `summary` | `Summary` | Per-day/per-session summary records. |
| `profile` | `SettingProfilesCollection` | Profile snapshot stream (repeated records). |
| `config` | `ConfigurationProfilesCollection` | Configuration snapshot (single record). |
| `event` | `UsageEvents-TherapyStatusEvents`, `TherapyEvents-RespiratoryEvents`, `SystemActivityEvents-FrequentActivityEvents`, `SystemActivityEvents-SporadicActivityEvents`, `SystemExceptionEvents-SystemErrors`, `SystemExceptionEvents-RecoverableErrors`, `SystemExceptionEvents-HumidifierErrors`, `SystemExceptionEvents-HeatedTubeErrors`, `DiagnosticExceptionEvents-AppErrors`, `DiagnosticExceptionEvents-FatalErrors`, `DiagnosticExceptionEvents-ResettableErrors`, `DiagnosticExceptionEvents-AlarmAppErrors`, `GUIActivityEvents`, `SurveyEvents`, `alarmEvents`, `alarmDiagnosticEvents`, `CellularActivityEvents` | Repeated event records: (type, start_ms, end_ms, duration_ms). |
| `periodic` | `TherapyOneMinutePeriodic` | Periodic measurement protobuf. |
| `periodic_compressed` | `DiagnosticTenMinutePeriodic`, `atmosphericPressure10min` | Two interleaved signal streams per record, each with its own compressed sample blob (not RC03). |
| `metric` | `MachineMetrics`, `MemoryMetrics`, `CellularDataUsage` | Single-record metric snapshot. |
| `rc03` | `RespiratoryFlow6p25Hz`, `MaskPressure6p25Hz`, `InspiratoryPressure0p5Hz`, `Leak0p5Hz` | Archived signal: protobuf wrapper around an RC03 compressed sample block. |
| `diag_vector` | `SoundcheckVector` | Multi-record diagnostic vector. |
| `diag_blob` | `AcousticSignatureV2` | Diagnostic blob; `AcousticSignatureV2` needs `maxFragmentSize >= 4096`. |
| `audio` | `RecordedSound` | Audio recording, gated by `SoundDownloadAllowed`. |

### Full enumeration

All 33 spool types accepted by `StartSpool` on the 15.8.4.0 firmware. The wire field column is the outer protobuf field number observed on a populated spool, or `--` when the spool has not yet been seen with data on a test device.

| Spool type | Family | Wire field | Gate | Group |
|------------|--------|------------|------|-------|
| `Summary` | `summary` | f2 | -- | session/profile data |
| `SettingProfilesCollection` | `profile` | f3 | -- | session/profile data |
| `ConfigurationProfilesCollection` | `config` | f23 | -- | session/profile data |
| `UsageEvents-TherapyStatusEvents` | `event` | f6 | -- | therapy data |
| `TherapyEvents-RespiratoryEvents` | `event` | -- | -- | therapy data |
| `TherapyOneMinutePeriodic` | `periodic` | f5 | -- | therapy data |
| `SystemActivityEvents-FrequentActivityEvents` | `event` | f10 | -- | system and diagnostic events |
| `SystemActivityEvents-SporadicActivityEvents` | `event` | f10 | -- | system and diagnostic events |
| `SystemExceptionEvents-SystemErrors` | `event` | -- | -- | system and diagnostic events |
| `SystemExceptionEvents-RecoverableErrors` | `event` | f7 | -- | system and diagnostic events |
| `SystemExceptionEvents-HumidifierErrors` | `event` | -- | -- | system and diagnostic events |
| `SystemExceptionEvents-HeatedTubeErrors` | `event` | -- | -- | system and diagnostic events |
| `DiagnosticExceptionEvents-AppErrors` | `event` | f9 | -- | system and diagnostic events |
| `DiagnosticExceptionEvents-FatalErrors` | `event` | -- | -- | system and diagnostic events |
| `DiagnosticExceptionEvents-ResettableErrors` | `event` | -- | -- | system and diagnostic events |
| `DiagnosticExceptionEvents-AlarmAppErrors` | `event` | -- | -- | system and diagnostic events |
| `GUIActivityEvents` | `event` | f13 | -- | system and diagnostic events |
| `SurveyEvents` | `event` | -- | -- | system and diagnostic events |
| `alarmEvents` | `event` | -- | -- | system and diagnostic events |
| `alarmDiagnosticEvents` | `event` | -- | -- | system and diagnostic events |
| `DiagnosticTenMinutePeriodic` | `periodic_compressed` | f17 | -- | periodic metrics |
| `MachineMetrics` | `metric` | f8 | -- | periodic metrics |
| `MemoryMetrics` | `metric` | f16 | -- | periodic metrics |
| `CellularActivityEvents` | `event` | f12 | -- | periodic metrics |
| `CellularDataUsage` | `metric` | f22 | -- | periodic metrics |
| `atmosphericPressure10min` | `periodic_compressed` | -- | -- | archived signals |
| `RespiratoryFlow6p25Hz` | `rc03` | f18 | -- | archived signals |
| `MaskPressure6p25Hz` | `rc03` | f19 | -- | archived signals |
| `InspiratoryPressure0p5Hz` | `rc03` | f21 | -- | archived signals |
| `Leak0p5Hz` | `rc03` | f20 | -- | archived signals |
| `SoundcheckVector` | `diag_vector` | f15 | -- | diagnostic blobs |
| `AcousticSignatureV2` | `diag_blob` | -- | -- | diagnostic blobs |
| `RecordedSound` | `audio` | -- | `SoundDownloadAllowed` | diagnostic blobs |

<!-- spool-registry: end -->

## Inner record shapes

### Event records

Most event spool records use the same inner record shape:

| Field | Meaning |
|-------|---------|
| `1` | event type/code |
| `2` | start timestamp, UTC milliseconds |
| `3` | end timestamp, UTC milliseconds |
| `4` | duration in milliseconds, when present |

The outer field number and wrapper depth vary by spool family, so the host
tool unwraps repeated field-1 event records conservatively and keeps unknown
event codes numeric unless a label table has been verified.

### TherapyOneMinutePeriodic records

`TherapyOneMinutePeriodic` uses outer protobuf field `5`. Each outer record
contains one or more per-signal messages, plus field `15`, which has been
observed as the sample interval in minutes.

Each per-signal message has this shape:

| Field | Meaning |
|-------|---------|
| `1` | status/kind marker, observed as `1` |
| `2` | start timestamp, UTC milliseconds |
| `3` | sample block |

The sample block is an int16 series. Fields `1..7` and `21` are headerless
second-difference/Rice streams using the same reconstruction formula as RC03.
Fields `8` and `9`, when present, are raw little-endian int16 arrays.

Decoded fields:

| Field | Name | CSV column | Scale |
|-------|------|------------|-------|
| `1` | Leak | `leak_l_min` | `raw * 1.2` L/min |
| `2` | InspiratoryPressure | `insp_pressure_cmH2O` | `raw / 5` cmH2O |
| `3` | ExpiratoryPressure | `exp_pressure_cmH2O` | `raw / 5` cmH2O |
| `4` | MinuteVentilation | `minute_vent_l_min` | `raw / 8` L/min |
| `5` | InspiratoryDuration | `insp_duration_s` | `raw / 50` seconds |
| `6` | RespiratoryRate | `resp_rate_bpm` | `raw` bpm |
| `7` | IeRatio | `ie_ratio_pct` | `raw * 4` percent |
| `8` | SpO2 | `spo2_pct` | `raw` percent |
| `9` | HeartRate | `heart_rate_bpm` | `raw` bpm |
| `21` | MIS | `mis` | `raw / 50`; exact meaning unresolved |

The field mapping and scales are verified against `Summary` percentile
records and observed oximetry samples.

### RC03 archived-signal records

The RC03 signal records are protobuf wrappers around a compressed sample
block. The inner record fields observed so far are:

| Field | Meaning |
|-------|---------|
| `1` | sample interval in milliseconds |
| `2` | start timestamp, UTC milliseconds |
| `3` | end timestamp, UTC milliseconds |
| `4` | RC03 compressed sample block |

The first byte of field `4` is the RC03 header length, followed by ASCII
`RC03`, six zigzag-varint format parameters, and compressed sample data. The
body starts with one or two signed little-endian 16-bit sample seeds. Remaining
samples are Rice-coded zigzag second differences:

```
delta2[n] = sample[n] - 2 * sample[n - 1] + sample[n - 2]
sample[n] = 2 * sample[n - 1] - sample[n - 2] + delta2[n]
```

On currently decoded archived signal blocks, parameter 4 is the Rice modulus
and parameter 1 gives the scale exponent. The host tool uses
`value = raw * (2 * 10 ** param1)`.
