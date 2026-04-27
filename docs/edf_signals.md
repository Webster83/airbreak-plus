# SX567 EDF Signal Reference

## BRP.edf -- Breath waveform (25 Hz, 60s records)

| # | Signal | var_id | UART | samples/rec | rate |
|---|--------|--------|------|-------------|------|
| 0 | Flow.40ms | 0x006B | RFL | 1500 | 25 Hz |
| 1 | Press.40ms | 0x0038 | MKP | 1500 | 25 Hz |
| 2 | TrigCycEvt.40ms | 0x0244 | TCV | 1500 | 25 Hz |
| 3 | Crc16 | 0x0023 | DCR | 1 | 1/rec |

## PLD.edf -- Per-breath stats (0.5 Hz, 60s records)

| # | Signal | var_id | UART | samples/rec | rate |
|---|--------|--------|------|-------------|------|
| 0 | MaskPress.2s | 0x0037 | MKF | 30 | 0.5 Hz |
| 1 | Press.2s | 0x0043 | MKI | 30 | 0.5 Hz |
| 2 | EprPress.2s | 0x0042 | MKE | 30 | 0.5 Hz |
| 3 | Leak.2s | 0x008D | LKF | 30 | 0.5 Hz |
| 4 | RespRate.2s | 0x00A0 | RRR | 30 | 0.5 Hz |
| 5 | TidVol.2s | 0x00A3 | TDD | 30 | 0.5 Hz |
| 6 | MinVent.2s | 0x0093 | MV5 | 30 | 0.5 Hz |
| 7 | TgtVent.2s | 0x002A | TGT | 30 | 0.5 Hz |
| 8 | IERatio.2s | 0x0082 | IER | 30 | 0.5 Hz |
| 9 | Snore.2s | 0x00A1 | SNI | 30 | 0.5 Hz |
| 10 | FlowLim.2s | 0x0071 | FFL | 30 | 0.5 Hz |
| 11 | B5ITime.2s | 0x0084 | IN5 | 30 | 0.5 Hz |
| 12 | B5ETime.2s | 0x0085 | EX5 | 30 | 0.5 Hz |
| 13 | Ti.2s | 0x0086 | INT | 30 | 0.5 Hz |
| 14 | Crc16 | 0x0023 | DCR | 1 | 1/rec |

## SAD.edf -- SpO2/pulse (1 Hz, 60s records)

| # | Signal | var_id | UART | samples/rec | rate |
|---|--------|--------|------|-------------|------|
| 0 | Pulse.1s | 0x0074 | HRT | 60 | 1 Hz |
| 1 | SpO2.1s | 0x0077 | SAO | 60 | 1 Hz |
| 2 | Crc16 | 0x0023 | DCR | 1 | 1/rec |

## OXH -- Oximetry summary (g[28], per-session)

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 0 | OXS | 0x0076 | OXS |
| 1 | HRS | 0x0073 | HRS |
| 2 | HRR | 0x0072 | HRR |
| 3 | SAS | 0x007C | SAS |
| 4 | SAR | 0x007B | SAR |
| 5 | NVS | 0x0075 | NVS |

## STR.edf -- Session statistics (1 record per session, 116 fields)

### Session header [0-3]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 0 | Date | 0x00BA | LSD |
| 1 | MaskOn | 0x00B8 | ONT |
| 2 | MaskOff | 0x00B5 | OFT |
| 3 | MaskEvents | 0x00B4 | MSE |

### Session timing [4-7]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 4 | Duration | 0x00B6 | OND |
| 5 | OnDuration | 0x00B7 | THD |
| 6 | PatientHours | 0x00BD | PHM |
| 7 | Mode | 0x020D | MOP |

### CPAP/common settings [8-15]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 8 | S.RampEnable | 0x0240 | RMA |
| 9 | S.RampTime | 0x01EF | RMT |
| 10 | S.C.StartPress | 0x01D2 | STP |
| 11 | S.C.Press | 0x0024 | IPC |
| 12 | S.EPR.ClinEnable | 0x0232 | EPA |
| 13 | S.EPR.EPREnable | 0x0233 | EPX |
| 14 | S.EPR.Level | 0x0070 | EPR |
| 15 | S.EPR.EPRType | 0x0234 | EPT |

### Bilevel settings [16-29]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 16 | S.BL.StartPress | 0x01DA | EPS |
| 17 | S.BL.IPAP | 0x0026 | IPP |
| 18 | S.BL.EPAP | 0x01D9 | EPP |
| 19 | S.EasyBreathe | 0x0217 | EBE |
| 20 | S.VA.StartPress | 0x01D8 | STV |
| 21 | S.VA.MaxIPAP | 0x01D6 | MXI |
| 22 | S.VA.MinEPAP | 0x01D5 | MNE |
| 23 | S.VA.PS | 0x01D7 | SPT |
| 24 | S.RiseEnable | 0x0218 | RSC |
| 25 | S.RiseTime | 0x01DB | RST |
| 26 | S.Cycle | 0x0245 | VCS |
| 27 | S.Trigger | 0x0246 | VTS |
| 28 | S.TiMax | 0x01DD | ITX |
| 29 | S.TiMin | 0x01DC | ITN |

### AutoSet settings [30-33]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 30 | S.AS.Comfort | 0x0221 | AFC |
| 31 | S.AS.StartPress | 0x01D4 | STU |
| 32 | S.AS.MaxPress | 0x0025 | MPA |
| 33 | S.AS.MinPress | 0x01D3 | MPI |

### ASV settings [34-42]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 34 | S.AV.StartPress | 0x01E3 | STE |
| 35 | S.AV.EPAP | 0x01E0 | EEP |
| 36 | S.AV.MaxPS | 0x01E2 | MXS |
| 37 | S.AV.MinPS | 0x01E1 | MNS |
| 38 | S.AA.StartPress | 0x01E8 | EAS |
| 39 | S.AA.MaxEPAP | 0x01E4 | EAX |
| 40 | S.AA.MinEPAP | 0x01E5 | EAI |
| 41 | S.AA.MaxPS | 0x01E7 | AXS |
| 42 | S.AA.MinPS | 0x01E6 | ANS |

### Common tail settings [43-56]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 43 | S.SmartStart | 0x0243 | SST |
| 44 | S.PtAccess | 0x0216 | ACC |
| 45 | S.ABFilter | 0x021C | ABF |
| 46 | S.LeakAlert | 0x0222 | ALR |
| 47 | S.Mask | 0x0213 | MSK |
| 48 | S.Tube | 0x0214 | TBT |
| 49 | S.ClimateControl | 0x0223 | CCO |
| 50 | S.HumEnable | 0x0224 | HMX |
| 51 | S.HumLevel | 0x0059 | HMS |
| 52 | S.TempEnable | 0x0226 | HTX |
| 53 | S.Temp | 0x005A | HTS |
| 54 | S.ExternalHum | 0x022B | HME |
| 55 | HeatedTube | 0x0225 | HTB |
| 56 | Humidifier | 0x0227 | HUM |

### EVE block 1 -- environmental/hardware stats [57-69]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 57 | BlowPress.95 | 0x003F | BP9 |
| 58 | BlowPress.5 | 0x0040 | BP5 |
| 59 | Flow.95 | 0x006E | RF9 |
| 60 | Flow.5 | 0x006F | RF5 |
| 61 | BlowFlow.50 | 0x005D | BFM |
| 62 | AmbHumidity.50 | 0x005F | ABM |
| 63 | HumTemp.50 | 0x0065 | HHM |
| 64 | HTubeTemp.50 | 0x0067 | HTM |
| 65 | HTubePow.50 | 0x0063 | TPM |
| 66 | HumPow.50 | 0x0069 | HPM |
| 67 | SpO2.50 | 0x0078 | SOM |
| 68 | SpO2.95 | 0x0079 | SO9 |
| 69 | SpO2.Max | 0x007A | SOX |

### Standalone CSL fields [70-72]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 70 | SpO2Thresh | 0x007D | SAU |
| 71 | CSR | 0x00AA | CSD |
| 72 | SpontCyc% | 0x00A8 | VCR |

### EVE block 2 -- therapy stats percentiles [73-103]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 73 | MaskPress.50 | 0x0039 | MSP |
| 74 | MaskPress.95 | 0x003A | PM9 |
| 75 | MaskPress.Max | 0x003B | PMA |
| 76 | TgtIPAP.50 | 0x0048 | PIM |
| 77 | TgtIPAP.95 | 0x0046 | PI9 |
| 78 | TgtIPAP.Max | 0x0047 | PIA |
| 79 | TgtEPAP.50 | 0x004B | PEM |
| 80 | TgtEPAP.95 | 0x0049 | PE9 |
| 81 | TgtEPAP.Max | 0x004A | PEA |
| 82 | Leak.50 | 0x008E | LKM |
| 83 | Leak.95 | 0x008C | LK9 |
| 84 | Leak.70 | 0x0092 | LK7 |
| 85 | Leak.Max | 0x0090 | LMX |
| 86 | MinVent.50 | 0x0097 | VTM |
| 87 | MinVent.95 | 0x0095 | VT9 |
| 88 | MinVent.Max | 0x0096 | VTA |
| 89 | RespRate.50 | 0x009F | RRM |
| 90 | RespRate.95 | 0x009D | RR9 |
| 91 | RespRate.Max | 0x009E | RRA |
| 92 | TidVol.50 | 0x00A7 | TVM |
| 93 | TidVol.95 | 0x00A5 | TV9 |
| 94 | TidVol.Max | 0x00A6 | TVA |
| 95 | IERatio.50 | 0x0081 | IEM |
| 96 | IERatio.95 | 0x007F | IE9 |
| 97 | IERatio.Max | 0x0080 | IEA |
| 98 | Ti.50 | 0x0088 | ISM |
| 99 | Ti.95 | 0x0089 | IS9 |
| 100 | Ti.Max | 0x008A | ISA |
| 101 | TgtVent.50 | 0x002D | VAM |
| 102 | TgtVent.95 | 0x002B | VA9 |
| 103 | TgtVent.Max | 0x002C | VAA |

### AEV -- apnea/hypopnea indices [104-110]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 104 | AHI | 0x004C | AHI |
| 105 | HI | 0x004F | HIS |
| 106 | AI | 0x004D | AIS |
| 107 | OAI | 0x0056 | CLI |
| 108 | CAI | 0x0057 | OPI |
| 109 | UAI | 0x0058 | UAI |
| 110 | RIN | 0x0050 | RIN |

### CSL tail -- faults + CRC [111-115]

| # | Signal | var_id | UART |
|---|--------|--------|------|
| 111 | Fault.Device | 0x0201 | SYS |
| 112 | Fault.Alarm | 0x0202 | SYT |
| 113 | Fault.Humidifier | 0x01FF | SYC |
| 114 | Fault.HeatedTube | 0x0200 | SYH |
| 115 | Crc16 | 0x0023 | DCR |
