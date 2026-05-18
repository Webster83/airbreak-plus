# AS11 RPC Event Reference

This document lists the live event-profile selectors accepted by
`SubscribeEvent` and the payload labels each selector carries. Protocol
mechanics (request fields, response shape, the `subscriptionId` cursor, the
unsubscribe state) are described in
[AS11 RPC Protocol](rpc_protocol.md#event-rpc). Historical event spools live
in [AS11 RPC Spool Reference](rpc_spools.md).

## Contents

- [Subscription selectors](#subscription-selectors)
- [Event families](#event-families)
  - [Therapy and usage](#therapy-and-usage)
  - [System activity](#system-activity)
  - [System exceptions](#system-exceptions)
  - [Diagnostic exceptions](#diagnostic-exceptions)
  - [Alarm profiles](#alarm-profiles)
- [Live subscription to spool mapping](#live-subscription-to-spool-mapping)
- [Open notes](#open-notes)

## Subscription selectors

Live selectors accepted by `SubscribeEvent.params.dataIds` on 15.8.4.0. Each
selector targets a single event profile leaf inside
`FlowGenerator.MeasurementProfiles`. The selector names are singular where the
profile leaf is singular (`...Event`, `...Error`, `...ErrorLogInfo`); matching
historical spool names are plural.

| Selector | Profile path | Notes |
|----------|--------------|-------|
| `UsageEvents-TherapyStatusEvent` | `UsageEvents.TherapyStatusEvents.TherapyStatusEvent` | therapy on/off and mode/status lifecycle |
| `TherapyEvents-RespiratoryEvent` | `TherapyEvents.RespiratoryEvents.RespiratoryEvent` | respiratory event reporting |
| `SystemActivityEvents-FrequentActivityEvent` | `SystemActivityEvents.FrequentActivityEvents.FrequentActivityEvent` | frequent system activity events |
| `SystemActivityEvents-SporadicActivityEvent` | `SystemActivityEvents.SporadicActivityEvents.SporadicActivityEvent` | sporadic system activity events |
| `SystemExceptionEvents-SystemError` | `SystemExceptionEvents.SystemErrors.SystemError` | system errors |
| `SystemExceptionEvents-RecoverableError` | `SystemExceptionEvents.RecoverableErrors.RecoverableError` | recoverable errors |
| `SystemExceptionEvents-HumidifierError` | `SystemExceptionEvents.HumidifierErrors.HumidifierError` | humidifier errors |
| `SystemExceptionEvents-HeatedTubeError` | `SystemExceptionEvents.HeatedTubeErrors.HeatedTubeError` | heated tube errors |
| `DiagnosticExceptionEvents-AppError` | `DiagnosticExceptionEvents.AppErrors.AppError` | application diagnostic errors |
| `DiagnosticExceptionEvents-FatalError` | `DiagnosticExceptionEvents.FatalErrors.FatalError` | fatal diagnostic errors |
| `DiagnosticExceptionEvents-ResettableError` | `DiagnosticExceptionEvents.ResettableErrors.ResettableError` | resettable diagnostic errors |
| `DiagnosticExceptionEvents-AlarmAppError` | `DiagnosticExceptionEvents.AlarmAppErrors.AlarmAppError` | alarm application errors |
| `DiagnosticExceptionEvents-ErrorLogInfo` | `DiagnosticExceptionEvents.ErrorLogInfos.ErrorLogInfo` | error-log info records |
| `alarmEvents` | `eventProfiles.alarmEvents` | alarm event profile |
| `alarmDiagnosticEvents` | `eventProfiles.alarmDiagnosticEvents` | alarm diagnostic event profile |

`SubscribeEvent` accepts unknown selector names and reports them as
`valid: false` in the response. Clients should reject a subscription if every
requested selector is invalid.

## Event families

Payload labels listed below come from the 15.8.4.0 firmware formatter tables
and the decoded historical event spools. They are grouped by the subscription
selector that delivers them; the matching spool namespace is in
[Live subscription to spool mapping](#live-subscription-to-spool-mapping).

### Therapy and usage

`UsageEvents-TherapyStatusEvent`:

- `NoUsage`, `MaskOff`, `MaskOn`, `PowerOff`
- `MaskFitStart`, `MaskFitStop`
- `TherapyStart`, `TherapyStop`
- `LearnTargetsStart`, `LearnTargetsStop`

`TherapyEvents-RespiratoryEvent`:

- `Hypopnea`, `CentralApnea`, `ObstructiveApnea`, `Apnea`
- `Rera` / `Arousal`
- `CsrStart`, `CsrEnd`

### System activity

`SystemActivityEvents-FrequentActivityEvent`:

- Lifecycle: `PowerUp`, `PowerDown`, `StandbyStarted`, `TherapyStarted`,
  `MaskfitStarted`, `WarmupStarted`, `WarmupStopped`, `CooldownStarted`,
  `CooldownStopped`, `BackupStarted`, `MockdownStarted`,
  `MockdownInterrupted`, `MockdownFinished`, `RampDownStarted`,
  `RampDownCompleted`
- Pressure control: `PressureStart`, `PressureStop`, `SmartStarted`,
  `SmartStopped`, `TherapyStopConfirmed`
- RPC stubs: `RpcStartTherapy`, `RpcStopTherapy`
- Button/UI: `ButtonPressStartStop`, `EnterClinicalMenu`, `ExitClinicalMenu`
- Bluetooth: `BluetoothConnected`, `BTDisconnected`,
  `BluetoothSecureSessionEstablished`, `BluetoothDiscoverable`,
  `BluetoothApplicationPairingAllowed`,
  `BluetoothApplicationPairingEstablished`,
  `BluetoothApplicationPairingDisallowed`,
  `BluetoothOximeterConnected`, `BluetoothOximeterPairingFailed`,
  `BluetoothOximeterDisconnected`
- Hardware: `SDCardInserted`, `HeatedTubeConnected`,
  `HeatedTubeDisconnected`, `AmalfiTubeConnected`, `HeatedTubeFailed`,
  `AlarmModuleComms`, `TxLink2Connected`
- Power supply: `PowerSupplyACMains90W`, `PowerSupplyDCMains90W`,
  `PowerSupply65W`
- Audio/soundcheck: `MicrophoneStartedRecording`,
  `MicrophoneStoppedRecording`, `SoundcheckStarted`, `SoundcheckCompleted`,
  `SoundcheckAcknowledged`, `CepstrumCalculated`
- Self-limit: `FrequentEventsFloodingMitigated`

`SystemActivityEvents-SporadicActivityEvent`:

- `DataResetStarted`, `CalibrationStarted`, `SystemErrorStarted`,
  `UpgradePrepStarted`, `TestDriveStarted`
- `FlightModeOn`, `FlightModeOff`
- RPC echoes: `RpcComplianceEraseRequest`,
  `RpcComplianceEraseRequestFailure`, `RpcEraseData`, `RpcEraseDataFailure`,
  `RpcError`, `RPCResetRequest`, `RPCInitiateUpgradeRequest`
- Storage: `FlashFormattedSettings`, `FlashFormattedData`,
  `FlashFormattedUpgrade`, `ComplianceEraseComplete`,
  `EventLogsEraseComplete`, `ResetToDefaultsComplete`, `EraseMediaComplete`

### System exceptions

`SystemExceptionEvents-SystemError`:

- `NoError`
- Motor: `MotorStallHW`, `MotorStallSW`, `MotorHwFault`, `MotorSticky`,
  `MotorFETs`, `MotorHwMitigationIC`
- Pressure: `FastOverPressure`, `PressureStuckHigh`, `PressureStuckLow`,
  `PressureStuckMid`, `PressureSensorDrift`, `PressureSensorsPlausibility`
- Flow: `NoFlowData`, `FlowSensorStuckLow`, `FlowSensorStuckHigh`
- Power/temp: `OverTemperature`, `OverVoltage`, `ImplausibleSupplyVoltage`,
  `FaultyHWFaultDetectionCircuitry`
- Settings: `SettingsReset`, `CalibrationReset`

`SystemExceptionEvents-RecoverableError`:

- `NoError`, `HoseBlocked`, `HoseDisconnected`, `HumidifierTubRemoved`

`SystemExceptionEvents-HumidifierError`:

- `NoError`, `OverCurrent`, `ProtectionFETShortCircuit`,
  `ControlFETShortCircuit`, `OpenCircuit`

`SystemExceptionEvents-HeatedTubeError`:

- `NoError`, `OverPower`, `OverTemperature`, `ProtectionFETShortCircuit`,
  `ControlFETShortCircuit`, `HeatingOpenCircuit`, `HeatingNTCOpenCircuit`,
  `SensorFail`, `OverCurrent`

### Diagnostic exceptions

`DiagnosticExceptionEvents-AppError`,
`DiagnosticExceptionEvents-FatalError`,
`DiagnosticExceptionEvents-ResettableError`,
`DiagnosticExceptionEvents-AlarmAppError`,
`DiagnosticExceptionEvents-ErrorLogInfo`

The static formatter labels for these selectors use the system-error and alarm-error
dictionaries listed above.

### Alarm profiles

`alarmEvents`:

- `HighLeakAlarm`, `NonVentedMaskAlarm`, `LowMinuteVentilationAlarm`,
  `ApneaAlarm`
- `RecoverableErrorHoseBlockedAlarm`,
  `RecoverableErrorHoseDisconnectedAlarm`,
  `RecoverableErrorHumidifierTubRemovedAlarm`
- `AlarmModuleCommunicationError`, `AlarmMute`

`alarmDiagnosticEvents`:

- Self-test: `IndicatorSelfTestInitiated`, `IndicatorSelfTestPass`,
  `IndicatorSelfTestFail`, `PrimaryLEDFail`, `SecondaryLEDFail`,
  `BuzzerFail`, `MuteButtonStuckOn`, `SelfTestInitiated`
- Supercap: `SupercapacitorSelfTestInitiated`,
  `SupercapacitorSelfTestPass`, `SupercapacitorSelfTestFail`,
  `SupercapacitorVoltage`, `SupercapacitorCapacitance`,
  `SupercapacitorESR`
- Upgrade lifecycle: `AlarmUpgradeInitiated`, `AlarmUpgradeSuccessful`,
  `AlarmUpgradeFailed`, `InitiateAlarmUpgradeRequested`,
  `InitiateAlarmUpgradeCompleted`, `InitiateAlarmUpgradeFailed`,
  `AlarmUpgradeFileTransferRequested`,
  `AlarmUpgradeFileTransferCompleted`,
  `AlarmUpgradeFileTransferFailed`, `ApplyAlarmUpgradeRequested`,
  `ApplyAlarmUpgradeCompleted`, `ApplyAlarmUpgradeFailed`

## Live subscription to spool mapping

`SubscribeEvent` selectors are singular leaves; `StartSpool` types are
plural containers. Both can target the same event family:

| Live subscription selector | Historical spool type |
|----------------------------|-----------------------|
| `UsageEvents-TherapyStatusEvent` | `UsageEvents-TherapyStatusEvents` |
| `TherapyEvents-RespiratoryEvent` | `TherapyEvents-RespiratoryEvents` |
| `SystemActivityEvents-FrequentActivityEvent` | `SystemActivityEvents-FrequentActivityEvents` |
| `SystemActivityEvents-SporadicActivityEvent` | `SystemActivityEvents-SporadicActivityEvents` |
| `SystemExceptionEvents-SystemError` | `SystemExceptionEvents-SystemErrors` |
| `SystemExceptionEvents-RecoverableError` | `SystemExceptionEvents-RecoverableErrors` |
| `SystemExceptionEvents-HumidifierError` | `SystemExceptionEvents-HumidifierErrors` |
| `SystemExceptionEvents-HeatedTubeError` | `SystemExceptionEvents-HeatedTubeErrors` |
| `DiagnosticExceptionEvents-AppError` | `DiagnosticExceptionEvents-AppErrors` |
| `DiagnosticExceptionEvents-FatalError` | `DiagnosticExceptionEvents-FatalErrors` |
| `DiagnosticExceptionEvents-ResettableError` | `DiagnosticExceptionEvents-ResettableErrors` |
| `DiagnosticExceptionEvents-AlarmAppError` | `DiagnosticExceptionEvents-AlarmAppErrors` |
| `DiagnosticExceptionEvents-ErrorLogInfo` | `DiagnosticExceptionEvents-ErrorLogInfos` |
| `alarmEvents` | `alarmEvents` |
| `alarmDiagnosticEvents` | `alarmDiagnosticEvents` |

Spool inner record shape for these event spools is documented in
[AS11 RPC Spool Reference](rpc_spools.md#event-records). The same field layout
is the strongest hint for live `EventNotification.params` decoding but should
not be treated as the final live schema until confirmed by a wire capture.
