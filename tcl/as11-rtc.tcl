# RTC date/time control for AS11
#
# STM32H753 RTC registers (base 0x58004000):
#   RTC_TR   0x58004000  Time (BCD: HH:MM:SS)
#   RTC_DR   0x58004004  Date (BCD: YY:WD:MM:DD)
#   RTC_SSR  0x58004008  Sub-second
#   RTC_ICSR 0x5800400C  Init/status (bit 7=INIT, bit 6=INITF)
#   RTC_WPR  0x58004024  Write protection (unlock: 0xCA, 0x53)
#
# Usage:
#   rtc::now               Read current date/time
#   rtc::set YYYY-MM-DD HH:MM:SS    Set date and time (UTC)
#   rtc::sync              Sync to host UTC time

namespace eval rtc {

    variable RTC_TR   0x58004000
    variable RTC_DR   0x58004004
    variable RTC_SSR  0x58004008
    variable RTC_ICSR 0x5800400C
    variable RTC_WPR  0x58004024

    variable DOW_NAME
    array set DOW_NAME { 1 Mon 2 Tue 3 Wed 4 Thu 5 Fri 6 Sat 7 Sun }

    proc _bcd_decode {val} {
        return [expr {(($val >> 4) & 0xF) * 10 + ($val & 0xF)}]
    }

    proc _bcd_encode {val} {
        set tens [expr {$val / 10}]
        set units [expr {$val % 10}]
        return [expr {($tens << 4) | $units}]
    }

    proc _dow {y m d} {
        # ISO: 1=Mon ... 7=Sun
        if {$m < 3} {
            set m [expr {$m + 12}]
            incr y -1
        }
        set h [expr {($d + (13*($m+1))/5 + $y + $y/4 - $y/100 + $y/400) % 7}]
        # Zeller: 0=Sat,1=Sun,...6=Fri -> ISO: 1=Mon...7=Sun
        set iso [expr {(($h + 5) % 7) + 1}]
        return $iso
    }

    proc _read_tr {} {
        variable RTC_TR
        return [mrw $RTC_TR]
    }

    proc _read_dr {} {
        variable RTC_DR
        return [mrw $RTC_DR]
    }

    proc _decode_tr {tr} {
        set h  [expr {(($tr >> 20) & 0x3) * 10 + (($tr >> 16) & 0xF)}]
        set m  [expr {(($tr >> 12) & 0x7) * 10 + (($tr >> 8) & 0xF)}]
        set s  [expr {(($tr >> 4) & 0x7) * 10 + ($tr & 0xF)}]
        return [list $h $m $s]
    }

    proc _decode_dr {dr} {
        set yt [expr {($dr >> 20) & 0xF}]
        set yu [expr {($dr >> 16) & 0xF}]
        set y  [expr {2000 + $yt * 10 + $yu}]
        set wd [expr {($dr >> 13) & 0x7}]
        set mt [expr {($dr >> 12) & 0x1}]
        set mu [expr {($dr >> 8) & 0xF}]
        set mo [expr {$mt * 10 + $mu}]
        set dt [expr {($dr >> 4) & 0x3}]
        set du [expr {$dr & 0xF}]
        set d  [expr {$dt * 10 + $du}]
        return [list $y $mo $d $wd]
    }

    proc now {} {
        variable DOW_NAME
        set tr [_read_tr]
        set dr [_read_dr]
        lassign [_decode_tr $tr] h m s
        lassign [_decode_dr $dr] y mo d wd
        set wdname ""
        if {[info exists DOW_NAME($wd)]} { set wdname $DOW_NAME($wd) }
        return [format "%04d-%02d-%02d %02d:%02d:%02d UTC (%s)" $y $mo $d $h $m $s $wdname]
    }

    proc _encode_tr {h m s} {
        set val 0
        set val [expr {$val | (([_bcd_encode $h] & 0x3F) << 16)}]
        set val [expr {$val | (([_bcd_encode $m] & 0x7F) << 8)}]
        set val [expr {$val | ([_bcd_encode $s] & 0x7F)}]
        return $val
    }

    proc _encode_dr {y mo d wd} {
        set yy [expr {$y - 2000}]
        set val 0
        set val [expr {$val | (([_bcd_encode $yy] & 0xFF) << 16)}]
        set val [expr {$val | (($wd & 0x7) << 13)}]
        set val [expr {$val | (([_bcd_encode $mo] & 0x1F) << 8)}]
        set val [expr {$val | ([_bcd_encode $d] & 0x3F)}]
        return $val
    }

    proc _rtc_unlock {} {
        variable RTC_WPR
        mww $RTC_WPR 0xCA
        mww $RTC_WPR 0x53
    }

    proc _rtc_lock {} {
        variable RTC_WPR
        mww $RTC_WPR 0xFF
    }

    proc _rtc_init_enter {} {
        variable RTC_ICSR
        set v [mrw $RTC_ICSR]
        set v [expr {$v | 0x80}]
        mww $RTC_ICSR $v
        # wait for INITF
        for {set i 0} {$i < 50} {incr i} {
            set v [mrw $RTC_ICSR]
            if {$v & 0x40} { return 1 }
            sleep 2
        }
        echo "WARNING: INITF timeout"
        return 0
    }

    proc _rtc_init_exit {} {
        variable RTC_ICSR
        set v [mrw $RTC_ICSR]
        set v [expr {$v & ~0x80}]
        mww $RTC_ICSR $v
    }

    proc _write {tr dr} {
        variable RTC_TR
        variable RTC_DR
        _rtc_unlock
        _rtc_init_enter
        mww $RTC_TR $tr
        mww $RTC_DR $dr
        _rtc_init_exit
        _rtc_lock
    }

    proc set_time {date time} {
        # date: YYYY-MM-DD  time: HH:MM:SS
        if {![regexp {^(\d{4})-(\d{2})-(\d{2})$} $date -> y mo d]} {
            error "Invalid date format. Use YYYY-MM-DD"
        }
        if {![regexp {^(\d{2}):(\d{2}):(\d{2})$} $time -> h m s]} {
            error "Invalid time format. Use HH:MM:SS"
        }

        set y  [scan $y %d]
        set mo [scan $mo %d]
        set d  [scan $d %d]
        set h  [scan $h %d]
        set m  [scan $m %d]
        set s  [scan $s %d]

        set wd [_dow $y $mo $d]

        set tr [_encode_tr $h $m $s]
        set dr [_encode_dr $y $mo $d $wd]

        _write $tr $dr
        echo "RTC set: [now]"
    }

    proc sync {} {
        set utc [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S} -gmt 1]
        lassign [split $utc] date time
        echo "Host UTC: $date $time"
        set_time $date $time
    }

    proc help {} {
        echo "RTC commands:"
        echo "  rtc::now                         Read current date/time"
        echo "  rtc::set_time YYYY-MM-DD HH:MM:SS   Set date and time (UTC)"
        echo "  rtc::sync                        Sync RTC to host UTC"
    }
}

if {[info level] == 0} {
    echo [rtc::help]
} else {
    echo "[info script] loaded."
    echo {    rtc::help for instructions}
}
