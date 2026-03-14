#!/usr/bin/env python3
"""
ResMed AirSense UART Configuration Tool

Read, write, dump, and restore device configuration variables over UART.
Variables are organized into groups matching the SETTINGS/*.tgt files.

"""

import serial
import argparse
import time
import sys
import json


GROUPS = {
    'AGL': ['AFC', 'STU', 'MPI', 'MPA'],
    'BGL': ['CCS', 'CCP', 'PNA', 'SRN', 'PCD', 'PCB', 'SNB', 'SNZ', 'FLZ', 'FLG',
            'PZH', 'PSH'],
    'CGL': ['STP', 'IPC'],
    'DGL': ['BRE', 'VCS', 'VTS', 'ITN', 'ITX', 'ITT', 'RRT'],
    'EGL': ['EPX', 'EPA', 'EPT', 'EPR'],
    'IGL': ['EBE', 'RST', 'RSC', 'EPS', 'EPP', 'IPP'],
    'MGL': ['QFC', 'ACC', 'HME', 'SCF', 'TLF', 'ALV', 'NMF', 'SPX', 'APX', 'LMA',
            'HLE', 'ALR', 'SST', 'RMT', 'RMA'],
    'NGL': ['ATH'],
    'PGL': ['ABF', 'HTF', 'HTS', 'HTX', 'HMS', 'HMX', 'CCO', 'TBT', 'MSK'],
    'QXH': ['EAS', 'AXS', 'EAI', 'EAX', 'ANS'],
    'QXJ': ['IVS', 'WMV', 'IBR', 'WPM', 'WPA', 'EPI', 'PHI', 'PHT'],
    'RGL': ['RPF', 'RCF', 'RXF', 'RDF', 'RPW', 'RCW', 'RXW', 'RDW', 'RPH', 'RCH',
            'RXH', 'RDH', 'RPO', 'RCM', 'RXM', 'RDM'],
    'SGL': ['IHU', 'PRD', 'TMU', 'LAN', 'LNC', 'MOP'],
    'UGL': ['TUD'],
    'VGL': ['SPT', 'STV', 'MNE', 'MXI'],
    'XGL': ['STE', 'MNS', 'MXS', 'EEP'],
}

# Build reverse lookup: var name > group
VAR_TO_GROUP = {}
for grp, vars_list in GROUPS.items():
    for v in vars_list:
        VAR_TO_GROUP[v] = grp

ALL_VARS = [v for grp in sorted(GROUPS) for v in GROUPS[grp]]

GROUP_ALIASES = {
    'all': list(GROUPS.keys()),
}

GROUP_DESC = {
    'AGL': 'AutoSet params',
    'BGL': 'Board/identity',
    'CGL': 'CPAP params',
    'DGL': 'Bilevel timing',
    'EGL': 'EPR params',
    'IGL': 'Bilevel pressure',
    'MGL': 'Machine settings',
    'NGL': 'Backlight?',
    'PGL': 'Peripherals/accessories',
    'QXH': 'ASVAuto params',
    'QXJ': 'iVAPS params',
    'RGL': 'Reminders/replacement',
    'SGL': 'System settings',
    'UGL': 'Usage data',
    'VGL': 'VAuto params',
    'XGL': 'ASV fixed params',
}

# Collected from ResScan metadata (M36 V26/V39), STR EDF col1 (g[13] PSTR), GUI descriptors (g[4]/g[6]/g[8])
VAR_DESC = {
    'ABF': 'AB Filter',
    'ACC': 'Patient Access',
    'AFC': 'AutoSet Comfort/Response',
    'ALR': 'Leak Alert',
    'ALV': 'Alarm Vol/Test',
    'ANS': 'ASVAuto Min PS',
    'APX': 'Apnea Alarm',
    'AXS': 'ASVAuto Max PS',
    'BRE': 'Backup Rate',
    'CCO': 'Climate Control',
    'EAI': 'ASVAuto Min EPAP',
    'EAS': 'ASVAuto Start EPAP',
    'EAX': 'ASVAuto Max EPAP',
    'EBE': 'Easy-Breathe',
    'EEP': 'ASV EPAP',
    'EPA': 'EPR Clinical Enable',
    'EPI': 'iVAPS EPAP',
    'EPP': 'Bilevel EPAP',
    'EPR': 'EPR Level',
    'EPS': 'Bilevel Start EPAP',
    'EPT': 'EPR Type',
    'EPX': 'EPR Patient Enable',
    'HLE': 'High Leak Alarm',
    'HME': 'Ext. Humidifier',
    'HMS': 'Humidity Level',
    'HMX': 'Humidity Enable',
    'HTF': 'Tube Temp',
    'HTS': 'Tube Temp',
    'HTX': 'Tube Temp Enable',
    'IBR': 'iVAPS Target Rate',
    'IHU': 'Height Units',
    'IPC': 'CPAP Set Pressure',
    'IPP': 'Bilevel IPAP',
    'ITN': 'Ti Min',
    'ITT': 'Ti',
    'ITX': 'Ti Max',
    'IVS': 'iVAPS Start EPAP',
    'LAN': 'Language',
    'LCA': 'LCD Text Active',
    'LCT': 'LCD Text',
    'LMA': 'Low MV Alarm',
    'LNC': 'Language Config Bitmask',
    'MFT': 'Mask Fitting Mode',
    'MNE': 'VAuto Min EPAP',
    'MNS': 'ASV Min PS',
    'MOP': 'Therapy Mode',
    'MPA': 'AutoSet Max Pressure',
    'MPI': 'AutoSet Min Pressure',
    'MSK': 'Mask Type',
    'MXI': 'VAuto Max IPAP',
    'MXS': 'ASV Max PS',
    'NMF': 'Non-Vent Mask',
    'PHI': 'Height',
    'PHT': 'Height',
    'PRD': 'Pressure Units',
    'QFC': 'Airplane Mode',
    'RCF': 'Recurrence Filter',
    'RCH': 'Recurrence Heated Tube',
    'RCM': 'Recurrence Mask',
    'RCW': 'Recurrence Water Tub',
    'RDF': 'Reminder Due: Filter',
    'RDH': 'Reminder Due: Tube',
    'RDM': 'Reminder Due: Mask',
    'RDW': 'Reminder Due: Water Tub',
    'REM': 'Factory Reset',
    'RMA': 'Ramp Enable',
    'RMT': 'Ramp Time',
    'RRT': 'Resp. Rate',
    'RPF': 'Recurrence Enable: Filter',
    'RPH': 'Recurrence Enable: Tube',
    'RPO': 'Recurrence Enable: Mask',
    'RPW': 'Recurrence Enable: Water Tub',
    'RSC': 'Rise Time Select',
    'RST': 'Rise Time',
    'RXF': 'Reminder Date Enable: Filter',
    'RXH': 'Reminder Date Enable: Tube',
    'RXM': 'Reminder Date Enable: Mask',
    'RXW': 'Reminder Date Enable: Water Tub',
    'SCF': 'Confirm Stop',
    'SPT': 'VAuto PS',
    'SPX': 'Low SpO2 Alarm',
    'SST': 'SmartStart',
    'STE': 'ASV Start EPAP',
    'STP': 'CPAP Start Pressure',
    'STU': 'AutoSet Start Pressure',
    'STV': 'VAuto Start EPAP',
    'TBT': 'Tube Type',
    'TLF': 'Therapy LED',
    'TMU': 'Temp. Units',
    'VCS': 'Cycle Sensitivity',
    'VTS': 'Trigger Sensitivity',
    'WMV': 'iVAPS Target Va',
    'WPA': 'iVAPS Max PS',
    'WPM': 'iVAPS Min PS',

    'BID': 'Bootloader ID',
    'CID': 'Config Software ID',
    'DAC': 'Date',
    'FGT': 'FG Type',
    'PCB': 'PCB ID',
    'PCD': 'Product Code',
    'PNA': 'Product Name',
    'SID': 'Software ID',
    'SRN': 'Serial Number',
    'TIC': 'Time',

    'AET': 'Apnea Event Type',
    'BLL': 'Jump to Bootloader',
    'BLS': 'Bootloader Status',
    'CSR': 'CSR Event Type',
    'HCM': 'Humidifier Operating Mode',
    'HOS': 'Humidifier Operating State',
    'HTB': 'Heated Tube Detected',
    'HUM': 'Humidifier Detected',
    'MST': 'Mask Status',
    'QCS': 'Cell Signal Strength',
    'QGI': 'Module Group',
    'QNC': 'Network Connection',
    'ROP': 'Run Mode Request',
    'ZRM': 'Run Mode',
    'ZRP': 'Is Ramping',

    'ATO': 'Activity Timeout',
    'BLE': 'Bootloader Error',
    'MID': 'Metadata ID',
    'RID': 'Region ID',
    'VID': 'Variant ID',
    'NOC': 'Occurrence Count',
    'AER': 'App Error Origin',
    'DCR': 'Record CRC',

    'AHI': 'AHI',
    'AIS': 'AI',
    'CLI': 'Central AI',
    'CSD': 'CSR Duration',
    'HIS': 'Hypopnea Index',
    'OPI': 'Obstructive AI',
    'RIN': 'RERA Index',
    'UAI': 'Unknown AI',

    'AEP': 'Avg EPR Pressure',
    'AIP': 'Avg Bilevel Pressure',
    'ATP': 'AutoSet Pressure',
    'BP5': 'Blower Pressure P5',
    'BP9': 'Blower Pressure P95',
    'HDR': 'Hose Drop',
    'MAP': 'Avg Mask Pressure',
    'MKE': 'EPR Pressure',
    'MKF': 'Filtered Mask Pressure',
    'MKI': 'Bilevel Mask Pressure',
    'MKP': 'Mask Pressure',
    'MSP': 'Median Pressure',
    'PE9': 'EPAP P95',
    'PEA': 'EPAP Max',
    'PEM': 'EPAP Median',
    'PI9': 'IPAP P95',
    'PIA': 'IPAP Max',
    'PIM': 'IPAP Median',
    'PM9': 'Pressure P95',
    'PMA': 'Pressure Max',
    'SPP': 'Set Pressure (runtime)',
    'TEP': 'Target EPAP',
    'TIP': 'Target IPAP',
    'LRP': 'Avg Low-Res Therapy Pressure',
    'LRE': 'Avg Low-Res EPR Pressure',

    'AFL': 'Avg Blower Flow',
    'BFF': 'Blower Flow Filtered',
    'BFM': 'Avg Blower Flow Median',
    'DFL': 'Differential Flow',
    'FFL': 'Fuzzy Flow Limit',
    'MV5': 'Minute Vent 5-Breath',
    'MVT': 'Mean Minute Vent',
    'RF5': 'Resp Flow P5',
    'RF9': 'Resp Flow P95',
    'RFL': 'Resp Flow',
    'VT9': 'Minute Vent P95',
    'VTA': 'Minute Vent Max',
    'VTM': 'Minute Vent Median',

    'LK7': 'Leak P70',
    'LK9': 'Leak P95',
    'LKF': 'Filtered Mask Leak',
    'LKM': 'Leak Median',
    'LKP': 'Leak (Hi-Res)',
    'LMX': 'Leak Max',
    'LYK': 'Mask Leak',

    'ATI': 'Avg Tidal Volume',
    'TDD': 'Tidal Volume 5-Breath',
    'TID': 'Tidal Volume',
    'TV9': 'Tidal Volume P95',
    'TVA': 'Tidal Volume Max',
    'TVM': 'Tidal Volume Median',

    'RR1': 'Resp Rate (realtime)',
    'RR9': 'Resp Rate P95',
    'RRA': 'Resp Rate Max',
    'RRM': 'Resp Rate Median',
    'RRR': 'Resp Rate (Hi-Res)',
    'SNI': 'Snore Index',

    'HRR': 'Heart Rate Raw',
    'HRS': 'Heart Rate Status',
    'HRT': 'Heart Rate',
    'NVS': 'Oximeter SW Version',
    'OXS': 'Oximetry Sequence',
    'SAO': 'SpO2',
    'SAR': 'SpO2 Raw',
    'SAS': 'SpO2 Status',
    'SAU': 'SpO2 Minutes Under Threshold',
    'SAV': 'Avg SpO2',
    'SO9': 'SpO2 P95',
    'SOM': 'SpO2 Median',
    'SOX': 'SpO2 Max',

    'ABH': 'Ambient Humidity',
    'ABM': 'Ambient Humidity Median',
    'HBP': 'Heated Tube PWM',
    'HHM': 'Humidifier Plate Temp Median',
    'HPM': 'Humidifier PWM Median',
    'HPT': 'Humidifier Plate Temp',
    'HTM': 'Heated Tube Temp Median',
    'HTT': 'Heated Tube Temp',
    'HUP': 'Humidifier PWM',
    'PPA': 'Plate Power Applied',
    'TPA': 'Tube Power Applied',
    'TPM': 'Heated Tube PWM Median',

    'CED': 'Compliance Erase Date',
    'FBD': 'First Breath Day',
    'FTD': 'First Therapy Day',
    'LSD': 'Current Session Date',
    'OFT': 'Mask Off Time',
    'OND': 'Mask On Duration',
    'ONT': 'Mask On Time',
    'PHM': 'Patient Hours',
    'THD': 'Therapy Duration',
    'MSE': 'Mask Events Count',

    'CET': 'CSR Event Time',
    'CSZ': 'CSR Zero Duration',
    'DUR': 'Apnea Duration',
    'ETI': 'Event Time',

    'SYC': 'Climate Control Error',
    'SYH': 'Heated Tube Error',
    'SYS': 'System Error',
    'SYT': 'System Error Two',
    'TYS': 'Transient System Error',

    'QCD': 'Cell Signal',
    'QCO': 'Module Operator',
    'QCV': 'Module Service Provider',
    'QSI': 'Module Serial Number',
    'QTI': 'Module Type',
    'QVI': 'Module SW Version',

    'SNB': 'Motor calibration something? PWM freq?',
    'FLZ': 'Flow calibration something?',
    'FLG': 'Flow calibration something?',
    'PZH': 'Pressure calibration something?',
    'PSH': 'Pressure calibration something?',
}

# Variable scaling metadata from ResScan protocol definition (M36 V39)
# Format: (scale_divisor, decimal_places, unit_string)
# Raw value ÷ scale_divisor = display value.  decimal_places for formatting.
# Only includes variables with non-trivial scaling.
VAR_SCALE = {
    # Pressures: raw value / 50
    'IPC': (50, 1, 'cmH2O'), 'STP': (50, 1, 'cmH2O'), 'MPA': (50, 1, 'cmH2O'),
    'MPI': (50, 1, 'cmH2O'), 'STU': (50, 1, 'cmH2O'), 'IPP': (50, 1, 'cmH2O'),
    'EPP': (50, 1, 'cmH2O'), 'EPS': (50, 1, 'cmH2O'), 'EEP': (50, 1, 'cmH2O'),
    'MNS': (50, 1, 'cmH2O'), 'MXS': (50, 1, 'cmH2O'), 'EAI': (50, 1, 'cmH2O'),
    'EAX': (50, 1, 'cmH2O'), 'ANS': (50, 1, 'cmH2O'), 'AXS': (50, 1, 'cmH2O'),
    'EPI': (50, 1, 'cmH2O'), 'WPM': (50, 1, 'cmH2O'), 'WPA': (50, 1, 'cmH2O'),
    'MXI': (50, 1, 'cmH2O'), 'MNE': (50, 1, 'cmH2O'), 'SPT': (50, 1, 'cmH2O'),
    'EAS': (50, 1, 'cmH2O'), 'STE': (50, 1, 'cmH2O'), 'STV': (50, 1, 'cmH2O'),
    'IVS': (50, 1, 'cmH2O'),
    'MKP': (50, 1, 'cmH2O'), 'MKF': (50, 1, 'cmH2O'), 'MKI': (50, 1, 'cmH2O'),
    'MKE': (50, 1, 'cmH2O'), 'MAP': (50, 1, 'cmH2O'), 'SPP': (50, 1, 'cmH2O'),
    'TEP': (50, 1, 'cmH2O'), 'TIP': (50, 1, 'cmH2O'), 'ATP': (50, 1, 'cmH2O'),
    'AEP': (50, 1, 'cmH2O'), 'AIP': (50, 1, 'cmH2O'), 'HDR': (50, 1, 'cmH2O'),
    'MSP': (50, 1, 'cmH2O'), 'PM9': (50, 1, 'cmH2O'), 'PMA': (50, 1, 'cmH2O'),
    'BP5': (50, 1, 'cmH2O'), 'BP9': (50, 1, 'cmH2O'),
    'PI9': (50, 1, 'cmH2O'), 'PIA': (50, 1, 'cmH2O'), 'PIM': (50, 1, 'cmH2O'),
    'PE9': (50, 1, 'cmH2O'), 'PEA': (50, 1, 'cmH2O'), 'PEM': (50, 1, 'cmH2O'),
    'EPR': (50, 0, 'cmH2O'),
    # Low-res pressure: raw / 5
    'LRP': (5, 1, 'cmH2O'), 'LRE': (5, 1, 'cmH2O'),
    # Tube temp: raw / 10
    'HTS': (10, 0, '°C'), 'HTF': (10, 0, '°F'),
    'HPT': (10, 0, '°C'), 'HHM': (10, 0, '°C'),
    'HTT': (10, 0, '°C'), 'HTM': (10, 0, '°C'),
    # Flow: raw / 500
    'RFL': (500, 2, 'L/s'), 'BFF': (500, 2, 'L/s'), 'DFL': (500, 2, 'L/s'),
    'RF9': (500, 2, 'L/s'), 'RF5': (500, 2, 'L/s'),
    # Leak: raw / 50
    'LK9': (50, 2, 'L/s'), 'LKF': (50, 2, 'L/s'), 'LKM': (50, 2, 'L/s'),
    'LKP': (50, 2, 'L/s'), 'LMX': (50, 2, 'L/s'), 'LYK': (50, 2, 'L/s'),
    'LK7': (50, 2, 'L/s'),
    # Blower flow: raw / 100
    'AFL': (100, 2, 'L/min'), 'BFM': (100, 2, 'L/min'),
    # Minute ventilation: raw / 8
    'MV5': (8, 1, 'L/min'), 'MVT': (8, 1, 'L/min'),
    'VT9': (8, 1, 'L/min'), 'VTA': (8, 1, 'L/min'), 'VTM': (8, 1, 'L/min'),
    # Resp rate: raw / 5
    'RR1': (5, 1, 'bpm'), 'RR9': (5, 1, 'bpm'), 'RRA': (5, 1, 'bpm'),
    'RRM': (5, 1, 'bpm'), 'RRR': (5, 0, 'bpm'),
    # Tidal volume: raw / 50
    'ATI': (50, 2, 'L'), 'TDD': (50, 2, 'L'), 'TID': (50, 2, 'L'),
    'TV9': (50, 2, 'L'), 'TVA': (50, 2, 'L'), 'TVM': (50, 2, 'L'),
    # Snore: raw / 50
    'SNI': (50, 2, ''),
    # AHI-family: raw / 10
    'AHI': (10, 1, '/hr'), 'AIS': (10, 1, '/hr'), 'HIS': (10, 1, '/hr'),
    'CLI': (10, 1, '/hr'), 'OPI': (10, 1, '/hr'), 'UAI': (10, 1, '/hr'),
    'RIN': (10, 1, '/hr'),
    # Fuzzy flow limit: raw / 100
    'FFL': (100, 2, ''),
    # Power applied: raw / 100
    'PPA': (100, 0, '%'), 'TPA': (100, 0, '%'),
}

# Enum option labels from ResScan metadata (M36 V39)
# Values are {int_value: 'label'}
ENUM_OPTIONS = {
    'MOP': {0: 'CPAP', 1: 'AutoSet', 2: 'APAP', 3: 'S', 4: 'ST', 5: 'T',
            6: 'VAuto', 7: 'ASV', 8: 'ASVAuto', 9: 'iVAPS', 10: 'PAC', 11: 'AutoSet Her'},
    'LAN': {0: 'English', 1: 'French', 2: 'German', 3: 'Italian', 4: 'Spanish (EU)',
            5: 'Spanish (US)', 6: 'Portuguese (EU)', 7: 'Portuguese (US)', 8: 'Dutch',
            9: 'Swedish', 10: 'Danish', 11: 'Norwegian', 12: 'Finnish', 13: 'Japanese',
            14: 'Russian', 15: 'Turkish', 16: 'Chinese (Trad)', 17: 'Chinese (Simp)',
            18: 'Polish', 19: 'Japanese (KN)', 20: 'Czech'},
    'MSK': {0: 'Pillows', 1: 'Full Face', 2: 'Nasal', 3: 'Pediatric'},
    'TBT': {0: 'SlimLine', 1: 'Standard', 2: '3m'},
    'REM': {0: 'Clinical', 1: 'Compliance', 2: 'Error Log', 3: 'All', 4: 'None'},
    'ACC': {0: 'Plus', 1: 'On'},
    'ABF': {0: 'No', 1: 'Yes'},
    'AFC': {0: 'Standard', 1: 'Soft'},
    'CCO': {0: 'Auto', 1: 'Manual'},
    'HMX': {0: 'Off', 1: 'On'},
    'HTX': {0: 'Off', 1: 'On', 2: 'Auto'},
    'TMU': {0: '°C', 1: '°F'},
    'QFC': {0: 'Off', 1: 'On'},
    'LCA': {0: 'Off', 1: 'On'},
    'EPA': {0: 'Off', 1: 'On'},
    'EPX': {0: 'Off', 1: 'On'},
    'EPT': {0: 'Ramp Only', 1: 'Full Time'},
    'MFT': {0: 'Off', 1: 'On'},
    'SST': {0: 'Off', 1: 'On'},
    'RMA': {0: 'Off', 1: 'On', 2: 'Auto'},
    'RPF': {0: 'Off', 1: 'On'}, 'RPO': {0: 'Off', 1: 'On'},
    'RPH': {0: 'Off', 1: 'On'}, 'RPW': {0: 'Off', 1: 'On'},
    'RXF': {0: 'Off', 1: 'On'}, 'RXM': {0: 'Off', 1: 'On'},
    'RXH': {0: 'Off', 1: 'On'}, 'RXW': {0: 'Off', 1: 'On'},
    'ZRM': {0: 'Reset', 1: 'Standby', 2: 'Backup', 3: 'Reset Compliance',
            4: 'Therapy', 5: 'Mask Fit', 6: 'Calibration', 7: 'System Error',
            8: 'Power Save', 9: 'Learn Target', 10: 'Upgrade', 11: 'Upgrade Prep'},
    'ROP': {0: 'Standby', 1: 'Normal', 2: 'Power Recovery', 3: 'Power Save',
            4: 'Calibration', 5: 'Upgrade'},
    'BLL': {0: 'Application', 1: 'Bootloader'},
    'BLS': {0: 'In Application', 1: 'In Bootloader', 2: 'In BL (Invalid App)'},
    'AET': {0: 'None', 1: 'Hypopnea', 2: 'Central', 3: 'Obstructive', 4: 'Apnea', 5: 'Arousal'},
    'HTB': {0: 'None', 1: '15mm', 2: '19mm'},
    'HUM': {0: 'End Cap', 1: 'Internal', 2: 'External'},
    'HOS': {0: 'None', 1: 'Off', 2: 'On'},
    'HCM': {0: 'None', 1: 'Manual', 2: 'Climate'},
    'QGI': {0: 'None', 1: 'Cellular'},
    'QCS': {0: 'None', 1: '1 Bar', 2: '2 Bars', 3: '3 Bars', 4: '4 Bars', 5: '5 Bars'},
    'QNC': {0: 'No Network', 1: 'Connected'},
    'ZRP': {0: 'No', 1: 'Yes'},
    'CSR': {0: 'None', 1: 'CSR Start', 2: 'CSR End'},
    'MST': {0: 'On', 1: 'Off', 2: 'Debounce'},
}


INFO_VARS = ['BID', 'SID', 'CID', 'PCB', 'SRN', 'PCD', 'PNA']


def format_value(name, raw_str):
    """Return a human-readable annotation for a raw hex value, or None."""
    if raw_str is None:
        return None
    raw_str = raw_str.strip()
    if name in ENUM_OPTIONS:
        try:
            val = int(raw_str, 16)
            label = ENUM_OPTIONS[name].get(val)
            if label:
                return label
        except ValueError:
            pass
    if name in VAR_SCALE:
        try:
            val = int(raw_str, 16)
            scale, decimals, unit = VAR_SCALE[name]
            if val > 0x7FFF and scale in (50, 5, 10, 500, 100, 8):
                val = val - 0x10000
            display = val / scale
            unit_str = f" {unit}" if unit else ""
            return f"{display:.{decimals}f}{unit_str}"
            #return f"{display:.{decimals}f}"
        except (ValueError, ZeroDivisionError):
            pass
    return None


def encode_value(name, user_str):
    """Convert a human-readable value to raw hex for the UART protocol.
    Returns hex string (e.g. '01F4') or None if variable has no known encoding.

    Raises ValueError if the variable has known encoding but the input is invalid.
    """
    user_str = user_str.strip()

    if name in ENUM_OPTIONS:
        lower = user_str.lower()
        for val, label in ENUM_OPTIONS[name].items():
            if label.lower() == lower:
                return f'{val:04X}'
        valid = ', '.join(ENUM_OPTIONS[name].values())
        raise ValueError(f"unknown option '{user_str}' for {name} (valid: {valid})")

    if name in VAR_SCALE:
        try:
            fval = float(user_str)
        except ValueError:
            raise ValueError(f"'{user_str}' is not a number for {name}")
        scale, decimals, unit = VAR_SCALE[name]
        raw = int(round(fval * scale))
        if raw < 0:
            raw = raw + 0x10000
        return f'{raw & 0xFFFF:04X}'

    return None


BDD_RATES = {57600: '0000', 115200: '0001', 460800: '0002'}
BDD_RATES_ORDERED = [460800, 115200, 57600]
PROBE_RATES = [57600, 115200, 460800]


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc

def escape_payload(data: bytes) -> bytes:
    return data.replace(b'U', b'UU')

def build_frame(frame_type: str, payload: bytes) -> bytes:
    escaped = escape_payload(payload)
    frame_len = 1 + 1 + 3 + len(escaped) + 4
    pre_crc = b'U' + frame_type.encode() + f'{frame_len:03X}'.encode() + escaped
    crc = crc16_ccitt(pre_crc)
    return pre_crc + f'{crc:04X}'.encode()

def build_q_frame(cmd: str) -> bytes:
    return build_frame('Q', cmd.encode())

def parse_responses(data: bytes) -> list:
    responses = []
    i = 0
    while i < len(data):
        if data[i:i+1] == b'U' and i+1 < len(data) and data[i+1:i+2] != b'U':
            try:
                ft = chr(data[i+1])
                if ft in 'EFKLPQR':
                    length = int(data[i+2:i+5], 16)
                    if i + length <= len(data):
                        raw_payload = data[i+5:i+length-4]
                        payload = raw_payload.replace(b'UU', b'U')
                        responses.append({'type': ft, 'payload': payload})
                        i += length
                        continue
            except (ValueError, IndexError):
                pass
        i += 1
    return responses

def read_responses(ser, timeout=1.0):
    old_timeout = ser.timeout
    ser.timeout = 0.02
    data = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = ser.read(4096)
        if chunk:
            data += chunk
            trail_deadline = time.time() + 0.02
            while time.time() < trail_deadline:
                chunk = ser.read(4096)
                if chunk:
                    data += chunk
                    trail_deadline = time.time() + 0.02
            break
    ser.timeout = old_timeout
    return data, parse_responses(data)

def send_cmd(ser, cmd_str, timeout=0.5, quiet=False):
    ser.reset_input_buffer()
    ser.write(build_q_frame(cmd_str))
    ser.flush()
    raw, responses = read_responses(ser, timeout=timeout)
    if not quiet:
        for r in responses:
            print(f"  [{r['type']}] {r['payload'].decode('ascii', errors='replace')}")
    return raw, responses

def sync_uart(ser):
    ser.reset_input_buffer()
    #ser.write(b'\x55' * 128)
    ser.flush()
    time.sleep(0.05)
    ser.reset_input_buffer()


def probe_baud(ser):
    for rate in PROBE_RATES:
        ser.baudrate = rate
        ser.reset_input_buffer()
        time.sleep(0.05)
        _, resp = send_cmd(ser, "G S #BID", timeout=0.3, quiet=True)
        if any(b'BID' in r['payload'] for r in resp):
            return rate
    return None

def switch_baud(ser, target, quiet=False):
    if target not in BDD_RATES or ser.baudrate == target:
        return ser.baudrate == target
    old = ser.baudrate
    if not quiet:
        print(f"[*] Switching baud: {old} -> {target} (BDD {BDD_RATES[target]})...")
    ser.reset_input_buffer()
    ser.write(build_q_frame(f"P S #BDD {BDD_RATES[target]}"))
    ser.flush()
    time.sleep(0.3)
    read_responses(ser, timeout=0.5)
    ser.baudrate = target
    sync_uart(ser)
    _, resp = send_cmd(ser, "G S #BID", timeout=0.5, quiet=True)
    if any(b'BID' in r['payload'] for r in resp):
        if not quiet:
            print(f"[+] Running at {target} baud")
        return True
    if not quiet:
        print(f"[!] No response at {target}, reverting")
    ser.baudrate = old
    sync_uart(ser)
    return False

def negotiate_best_baud(ser):
    for rate in BDD_RATES_ORDERED:
        if rate == ser.baudrate:
            return rate
        if switch_baud(ser, rate):
            return rate
    return ser.baudrate


def get_var(ser, name):
    """Read a single variable. Returns (frame_type, value_str).
    R-frame: ('R', value).  E-frame: ('E', error_code).  No response: (None, None)."""
    _, resp = send_cmd(ser, f"G S #{name}", timeout=0.5, quiet=True)
    for r in resp:
        payload = r['payload'].decode('ascii', errors='replace')
        if '=' in payload:
            return (r['type'], payload.split('=', 1)[1].strip())
    return (None, None)

def set_var(ser, name, value):
    """Write a single variable. Returns (frame_type, value_str).
    R-frame: ('R', echo_value).  E-frame: ('E', error_code).  No response: (None, None)."""
    _, resp = send_cmd(ser, f"P S #{name} {value}", timeout=0.5, quiet=True)
    for r in resp:
        payload = r['payload'].decode('ascii', errors='replace')
        if '=' in payload:
            return (r['type'], payload.split('=', 1)[1].strip())
    return (None, None)

def get_var_caps(ser, name):
    """Read variable capabilities. Returns (frame_type, value_str)."""
    _, resp = send_cmd(ser, f"G C #{name}", timeout=0.5, quiet=True)
    for r in resp:
        payload = r['payload'].decode('ascii', errors='replace')
        if '=' in payload:
            return (r['type'], payload.split('=', 1)[1].strip())
    return (None, None)


def resolve_groups(group_names):
    """Resolve group names/aliases to a list of variable names."""
    var_names = []
    for name in group_names:
        upper = name.upper()
        if upper in GROUP_ALIASES:
            for grp in GROUP_ALIASES[upper]:
                var_names.extend(GROUPS[grp])
        elif upper in GROUPS:
            var_names.extend(GROUPS[upper])
        elif upper in VAR_TO_GROUP:
            var_names.append(upper)
        else:
            # Treat as raw variable name - let the device decide
            var_names.append(upper)
    return var_names

def exclude_vars(var_names, exclude_groups=None, exclude_vars_list=None):
    """Remove variables by group or individual name."""
    excluded = set()
    if exclude_groups:
        for grp in exclude_groups:
            upper = grp.upper()
            if upper in GROUPS:
                excluded.update(GROUPS[upper])
            else:
                print(f"[!] Unknown group: {grp}")
    if exclude_vars_list:
        excluded.update(v.upper() for v in exclude_vars_list)
    return [v for v in var_names if v not in excluded]


def cmd_info(ser, verbose=False):
    print("[*] Device info:")
    for var in INFO_VARS:
        ft, val = get_var(ser, var)
        desc = VAR_DESC.get(var, '')
        desc_str = f"  ({desc})" if verbose and desc else ""
        if ft == 'R':
            print(f"  {var:4s} = {val}{desc_str}")
        elif ft == 'E':
            print(f"  {var:4s} = [E] {val}{desc_str}")
        else:
            print(f"  {var:4s} = (no response){desc_str}")

def cmd_get(ser, targets, verbose=False):
    """Get one or more variables/groups."""
    var_names = resolve_groups(targets)
    if var_names is None:
        return 1
    for name in var_names:
        ft, val = get_var(ser, name)
        grp = VAR_TO_GROUP.get(name, '-')
        desc = VAR_DESC.get(name, '')
        desc_str = f"({desc})" if verbose and desc else ""
        if ft == 'R':
            ann = format_value(name, val)
            ann_str = f"[{ann}] " if ann else ""
            sep = "# " if ann or desc_str else ""
            print(f"  [{grp}] {name:4s} = {val} {sep}{ann_str}{desc_str}")
        elif ft == 'E':
            print(f"  [{grp}] {name:4s} = {val} # ERROR {desc_str}")
        else:
            print(f"  [{grp}] {name:4s} = # NO-RESPONSE {desc_str}")
    return 0

def cmd_set(ser, var_name, value):
    """Set a single variable (raw hex value)."""
    name = var_name.upper()
    grp = VAR_TO_GROUP.get(name, '-')
    _, old_val = get_var(ser, name)
    print(f"  [{grp}] {name} = {old_val} -> {value}")
    ft, resp = set_var(ser, name, value)
    if ft == 'R':
        _, new_val = get_var(ser, name)
        print(f"  [{grp}] {name} = {new_val} (confirmed)")
        return 0
    elif ft == 'E':
        print(f"  [!] {name} = {resp} # ERROR")
        return 1
    else:
        print(f"  [!] {name} = # NO-RESPONSE")
        return 1

def cmd_setv(ser, var_name, value):
    """Set a variable using scaled/human-readable value (e.g. 10.0 for cmH2O, AutoSet for mode)."""
    name = var_name.upper()
    grp = VAR_TO_GROUP.get(name, '-')
    raw = encode_value(name, value)
    if raw is None:
        print(f"  [!] {name}: no known scaling or enum — use 'set' with raw hex")
        return 1
    oft, old_val = get_var(ser, name)
    old_ann = format_value(name, old_val) if oft == 'R' else None
    old_str = f"{old_val} ({old_ann})" if old_ann else str(old_val)
    print(f"  [{grp}] {name}: {value} -> {raw}")
    ft, resp = set_var(ser, name, raw)
    if ft == 'R':
        _, new_val = get_var(ser, name)
        new_ann = format_value(name, new_val)
        new_str = f"{new_val} ({new_ann})" if new_ann else str(new_val)
        print(f"  [{grp}] {name} = {old_str} -> {new_str}")
        return 0
    elif ft == 'E':
        print(f"  [!] {name} = {resp} # ERROR")
        return 1
    else:
        print(f"  [!] {name} = # NO-RESPONSE")
        return 1

def cmd_dump(ser, groups=None, exclude_groups=None, exclude_vars_list=None):
    """Dump variables to dict. Returns {group: {var: value}}."""
    if groups:
        var_names = resolve_groups(groups)
    else:
        var_names = resolve_groups(['all'])
    if var_names is None:
        return None

    var_names = exclude_vars(var_names, exclude_groups, exclude_vars_list)

    result = {}
    total = len(var_names)
    for i, name in enumerate(var_names):
        grp = VAR_TO_GROUP.get(name, 'UNK')
        ft, val = get_var(ser, name)
        if grp not in result:
            result[grp] = {}
        result[grp][name] = val if ft == 'R' else None
        sys.stdout.write(f"\r  Reading: {i+1}/{total} ({name})...")
        sys.stdout.flush()
    print(f"\r  Read {total} variables.              ")
    return result

def cmd_restore(ser, data, exclude_groups=None, exclude_vars_list=None, dry_run=False):
    """Restore variables from dump dict."""
    changes = []
    for grp in sorted(data.keys()):
        for name, value in sorted(data[grp].items()):
            if value is None:
                continue
            changes.append((grp, name, value))

    # exclusions
    excluded = set()
    if exclude_groups:
        for grp in exclude_groups:
            upper = grp.upper()
            if upper in GROUPS:
                excluded.update(GROUPS[upper])
    if exclude_vars_list:
        excluded.update(v.upper() for v in exclude_vars_list)

    changes = [(g, n, v) for g, n, v in changes if n not in excluded]

    if not changes:
        print("[!] No variables to restore.")
        return 1

    print(f"[*] Restoring {len(changes)} variables...")
    errors = 0
    for i, (grp, name, value) in enumerate(changes):
        _, current = get_var(ser, name)
        if current == value:
            sys.stdout.write(f"\r  {i+1}/{len(changes)} {name}: unchanged    ")
            sys.stdout.flush()
            continue

        if dry_run:
            print(f"\r  [DRY] [{grp}] {name}: {current} -> {value}")
            continue

        ft, resp = set_var(ser, name, value)
        if ft == 'R':
            sys.stdout.write(f"\r  {i+1}/{len(changes)} {name}: {current} -> {value}    ")
            sys.stdout.flush()
        else:
            err = f": {resp}" if resp else ""
            print(f"\r  [!] [{grp}] {name}: FAILED to set {value}{err}")
            errors += 1

    print(f"\r  Restore complete. {len(changes)} variables, {errors} errors.          ")
    return 0 if errors == 0 else 1

def cmd_list(groups=None):
    """List known variables with their groups and descriptions (offline, no device query)."""
    if groups:
        group_list = []
        for g in groups:
            upper = g.upper()
            if upper in GROUPS:
                group_list.append(upper)
            else:
                print(f"[!] Unknown group: {g}")
                return 1
    else:
        group_list = sorted(GROUPS.keys())

    for grp in group_list:
        vars_list = GROUPS[grp]
        grp_desc = GROUP_DESC.get(grp, '')
        header = f"  {grp} ({len(vars_list)} vars)"
        if grp_desc:
            header += f" — {grp_desc}"
        print(f"\n{header}:")
        for name in vars_list:
            desc = VAR_DESC.get(name, '')
            if desc:
                print(f"    {name:4s}  {desc}")
            else:
                print(f"    {name:4s}")
    return 0

def cmd_caps(ser, groups=None, verbose=False):
    """Query variable limits/capabilities from device (G S # + G C #)."""
    if groups:
        group_list = []
        for g in groups:
            upper = g.upper()
            if upper in GROUPS:
                group_list.append(upper)
            elif upper in VAR_TO_GROUP:
                group_list.append(('_single', upper))
            else:
                print(f"[!] Unknown group or variable: {g}")
                return 1
    else:
        group_list = sorted(GROUPS.keys())

    for item in group_list:
        if isinstance(item, tuple) and item[0] == '_single':
            name = item[1]
            grp = VAR_TO_GROUP.get(name, '-')
            desc = VAR_DESC.get(name, '')
            vft, val = get_var(ser, name)
            cft, caps = get_var_caps(ser, name)
            if vft == 'R':
                ann = format_value(name, val)
                val_str = f"{val} ({ann})" if ann else val
            elif vft == 'E':
                val_str = f"[E] {val}"
            else:
                val_str = "(no response)"
            caps_str = f"  caps: {caps}" if cft == 'R' else ""
            desc_str = f"  ({desc})" if verbose and desc else ""
            print(f"  [{grp}] {name:4s} = {val_str}{caps_str}{desc_str}")
        else:
            grp = item
            vars_list = GROUPS[grp]
            grp_desc = GROUP_DESC.get(grp, '')
            header = f"  {grp} ({len(vars_list)} vars)"
            if grp_desc:
                header += f" — {grp_desc}"
            print(f"\n{header}:")
            for name in vars_list:
                desc = VAR_DESC.get(name, '')
                vft, val = get_var(ser, name)
                cft, caps = get_var_caps(ser, name)
                if vft == 'R':
                    ann = format_value(name, val)
                    val_str = f"{val} ({ann})" if ann else val
                elif vft == 'E':
                    val_str = f"[E] {val}"
                else:
                    val_str = "(no response)"
                caps_str = f"  caps: {caps}" if cft == 'R' else ""
                desc_str = f"  ({desc})" if verbose and desc else ""
                print(f"    {name:4s} = {val_str}{caps_str}{desc_str}")
    return 0


def connect(ser, baud_arg):
    """Connect and probe or set baud rate. Returns True on success."""
    if baud_arg == 'auto':
        print("[*] Probing device...")
        baud = probe_baud(ser)
        if not baud:
            print("[!] Device not responding at any known baud rate")
            return False
        print(f"[+] Device responding at {baud} baud")
        ser.baudrate = baud
    else:
        rate = int(baud_arg)
        ser.baudrate = rate
        _, resp = send_cmd(ser, "G S #BID", timeout=0.5, quiet=True)
        if not any(b'BID' in r['payload'] for r in resp):
            print(f"[!] No response at {rate} baud")
            return False
        print(f"[+] Device responding at {rate} baud")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='ResMed AirSense UART Configuration Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  info                          Show device identity
  get <var|group|all>           Read variables
  set <var> <value>             Write a variable
  dump                          Dump all variables to JSON
  restore                       Restore variables from JSON
  list                          List known variables and descriptions (offline)
  caps                          Query variable limits from device

Groups: """ + ', '.join(sorted(GROUPS.keys())) + """

Examples:
  %(prog)s -p /dev/ttyACM0 info
  %(prog)s -p /dev/ttyACM0 get MGL
  %(prog)s -p /dev/ttyACM0 get SPT
  %(prog)s -p /dev/ttyACM0 set SPT 0001
  %(prog)s -p /dev/ttyACM0 setv IPC 10.0            # 10.0 cmH2O -> 01F4
  %(prog)s -p /dev/ttyACM0 setv MOP AutoSet          # enum label -> 0001
  %(prog)s -p /dev/ttyACM0 dump -o config.json
  %(prog)s -p /dev/ttyACM0 dump --groups MGL EGL -o therapy.json
  %(prog)s -p /dev/ttyACM0 restore -i config.json
  %(prog)s -p /dev/ttyACM0 restore -i config.json --exclude-groups BGL
  %(prog)s list
  %(prog)s list --groups MGL DGL
  %(prog)s -p /dev/ttyACM0 caps --groups MGL
""")

    parser.add_argument('-p', '--port', help='Serial port (required for device commands)')
    parser.add_argument('--baud', default='auto', help='Baud rate: auto, 57600, 115200, 460800')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show variable descriptions')

    sub = parser.add_subparsers(dest='command', help='Command')

    sub.add_parser('info', help='Show device identity')

    p_get = sub.add_parser('get', help='Read variables')
    p_get.add_argument('targets', nargs='+', help='Variable names, group names, or "all"')

    p_set = sub.add_parser('set', help='Write a variable')
    p_set.add_argument('var', help='Variable name (3 chars)')
    p_set.add_argument('value', help='Value to set (hex string)')

    p_setv = sub.add_parser('setv', help='Write a variable (scaled/human value)')
    p_setv.add_argument('var', help='Variable name (3 chars)')
    p_setv.add_argument('value', help='Scaled value (e.g. 10.0 for cmH2O) or enum label (e.g. AutoSet)')

    p_dump = sub.add_parser('dump', help='Dump variables to JSON')
    p_dump.add_argument('-o', '--output', required=True, help='Output JSON file')
    p_dump.add_argument('--groups', nargs='+', help='Only dump these groups')
    p_dump.add_argument('--exclude-groups', nargs='+', help='Exclude these groups')
    p_dump.add_argument('--exclude-vars', nargs='+', help='Exclude these variables')

    p_restore = sub.add_parser('restore', help='Restore variables from JSON')
    p_restore.add_argument('-i', '--input', required=True, help='Input JSON file')
    p_restore.add_argument('--exclude-groups', nargs='+', help='Skip these groups')
    p_restore.add_argument('--exclude-vars', nargs='+', help='Skip these variables')
    p_restore.add_argument('--dry-run', action='store_true', help='Show changes without writing')

    p_raw = sub.add_parser('raw', help='Send raw command')
    p_raw.add_argument('cmd', nargs='+', help='Raw command string (e.g. "G S #BID")')

    p_list = sub.add_parser('list', help='List known variables and descriptions (offline)')
    p_list.add_argument('--groups', nargs='+', help='Only list these groups')

    p_caps = sub.add_parser('caps', help='Query variable values and limits from device')
    p_caps.add_argument('--groups', nargs='+', help='Groups or variable names to query')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'list':
        return cmd_list(args.groups)

    # All other commands need a serial port
    if not args.port:
        print("[!] --port is required for this command")
        return 1

    ser = serial.Serial(args.port, 57600, timeout=1.0)

    try:
        if not connect(ser, args.baud):
            return 1

        if args.command == 'info':
            return cmd_info(ser, verbose=args.verbose)

        elif args.command == 'get':
            return cmd_get(ser, args.targets, verbose=args.verbose)

        elif args.command == 'set':
            return cmd_set(ser, args.var, args.value)

        elif args.command == 'setv':
            try:
                return cmd_setv(ser, args.var, args.value)
            except ValueError as e:
                print(f"  [!] {e}")
                return 1

        elif args.command == 'dump':
            data = cmd_dump(ser, args.groups, args.exclude_groups, args.exclude_vars)
            if data is None:
                return 1
            with open(args.output, 'w') as f:
                json.dump(data, f, indent=2, sort_keys=True)
            print(f"[+] Saved to {args.output}")
            return 0

        elif args.command == 'restore':
            with open(args.input) as f:
                data = json.load(f)
            return cmd_restore(ser, data, args.exclude_groups, args.exclude_vars, args.dry_run)

        elif args.command == 'raw':
            cmd_str = ' '.join(args.cmd)
            send_cmd(ser, cmd_str, timeout=1.0)
            return 0

        elif args.command == 'caps':
            return cmd_caps(ser, args.groups, verbose=args.verbose)

    finally:
        ser.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
