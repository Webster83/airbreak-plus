# ============================================================
# ResMed AirSense 10 UI Theme Patcher
# ============================================================

namespace eval theme {

    # --------------------------------------------------------
    # Address layout
    # --------------------------------------------------------
    variable base_addr 0xf26f8
    variable end_addr  0xf279c
    variable entry_len 4

    # --------------------------------------------------------
    # Theme definitions (single source of truth)
    # --------------------------------------------------------
    variable themes {
        default {
            0xf271c 0099cc00
            0xf26f8 ffffff00 0xf2714 ffffff00 0xf2720 ffffff00
            0xf2738 ffffff00 0xf273c ffffff00 0xf2740 ffffff00
            0xf274c ffffff00 0xf2768 ffffff00 0xf2774 ffffff00
            0xf278c ffffff00 0xf2790 ffffff00 0xf2794 ffffff00
            0xf26fc 96969600 0xf2704 96969600 0xf2750 96969600
            0xf2758 96969600 0xf276c 96969600
            0xf2700 64646400 0xf2754 64646400
            0xf2708 40404000 0xf270c 40404000 0xf2728 40404000
            0xf2744 40404000 0xf275c 40404000 0xf2760 40404000
            0xf277c 40404000 0xf2798 40404000
            0xf2710 00000000 0xf272c 00000000 0xf2748 00000000
            0xf2764 00000000 0xf2780 00000000 0xf279c 00000000
        }

        asmageddon {
            0xf271c cc330000
            0xf26f8 ffbb4400 0xf2714 ffbb4400 0xf2720 ffbb4400
            0xf2738 ffbb4400 0xf273c ffbb4400 0xf2740 ffbb4400
            0xf274c ffbb4400 0xf2768 ffbb4400 0xf2774 ffbb4400
            0xf278c ffbb4400 0xf2790 ffbb4400 0xf2794 ffbb4400
            0xf26fc 96484800 0xf2704 96484800 0xf2750 96484800
            0xf2758 96484800 0xf276c 96484800
            0xf2700 64323200 0xf2754 64323200
            0xf2708 40202000 0xf270c 40202000 0xf2728 40202000
            0xf2744 40202000 0xf275c 40202000 0xf2760 40202000
            0xf277c 40202000 0xf2798 40202000
            0xf2710 08000800 0xf272c 08000800 0xf2748 08000800
            0xf2764 08000800 0xf2780 08000800 0xf279c 08000800
        }

        asmageddon_dark {
            0xf271c 70180c00
            0xf26f8 f3885100 0xf2714 f3885100 0xf2720 f3885100
            0xf2738 f3885100 0xf273c f3885100 0xf2740 f3885100
            0xf274c f3885100 0xf2768 f3885100 0xf2774 f3885100
            0xf278c f3885100 0xf2790 f3885100 0xf2794 f3885100
            0xf26fc 50282800 0xf2704 50282800 0xf2750 50282800
            0xf2758 50282800 0xf276c 50282800
            0xf2700 2c161600 0xf2754 2c161600
            0xf2708 11080800 0xf270c 11080800 0xf2728 11080800
            0xf2744 11080800 0xf275c 11080800 0xf2760 11080800
            0xf277c 11080800 0xf2798 11080800
            0xf2710 08000800 0xf272c 08000800 0xf2748 08000800
            0xf2764 08000800 0xf2780 08000800 0xf279c 08000800
        }

        night_vision {
            0xf271c 66000000
            0xf26f8 e6c0c000 0xf2714 e6c0c000 0xf2720 e6c0c000
            0xf2738 e6c0c000 0xf273c e6c0c000 0xf2740 e6c0c000
            0xf274c e6c0c000 0xf2768 e6c0c000 0xf2774 e6c0c000
            0xf278c e6c0c000 0xf2790 e6c0c000 0xf2794 e6c0c000
            0xf26fc 4a2a2a00 0xf2704 4a2a2a00 0xf2750 4a2a2a00
            0xf2758 4a2a2a00 0xf276c 4a2a2a00
            0xf2700 32181800 0xf2754 32181800
            0xf2708 160a0a00 0xf270c 160a0a00 0xf2728 160a0a00
            0xf2744 160a0a00 0xf275c 160a0a00 0xf2760 160a0a00
            0xf277c 160a0a00 0xf2798 160a0a00
            0xf2710 00000000 0xf272c 00000000 0xf2748 00000000
            0xf2764 00000000 0xf2780 00000000 0xf279c 00000000
        }

        night_toned {
            0xf271c 00668800
            0xf26f8 d8d8d800 0xf2714 d8d8d800 0xf2720 d8d8d800
            0xf2738 d8d8d800 0xf273c d8d8d800 0xf2740 d8d8d800
            0xf274c d8d8d800 0xf2768 d8d8d800 0xf2774 d8d8d800
            0xf278c d8d8d800 0xf2790 d8d8d800 0xf2794 d8d8d800
            0xf26fc 80808000 0xf2704 80808000 0xf2750 80808000
            0xf2758 80808000 0xf276c 80808000
            0xf2700 58585800 0xf2754 58585800
            0xf2708 30303000 0xf270c 30303000 0xf2728 30303000
            0xf2744 30303000 0xf275c 30303000 0xf2760 30303000
            0xf277c 30303000 0xf2798 30303000
            0xf2710 00000000 0xf272c 00000000 0xf2748 00000000
            0xf2764 00000000 0xf2780 00000000 0xf279c 00000000
        }

        night_dark {
            0xf271c 00557700
            0xf26f8 c8c8c800 0xf2714 c8c8c800 0xf2720 c8c8c800
            0xf2738 c8c8c800 0xf273c c8c8c800 0xf2740 c8c8c800
            0xf274c c8c8c800 0xf2768 c8c8c800 0xf2774 c8c8c800
            0xf278c c8c8c800 0xf2790 c8c8c800 0xf2794 c8c8c800
            0xf26fc 78787800 0xf2704 78787800 0xf2750 78787800
            0xf2758 78787800 0xf276c 78787800
            0xf2700 50505000 0xf2754 50505000
            0xf2708 28282800 0xf270c 28282800 0xf2728 28282800
            0xf2744 28282800 0xf275c 28282800 0xf2760 28282800
            0xf277c 28282800 0xf2798 28282800
            0xf2710 00000000 0xf272c 00000000 0xf2748 00000000
            0xf2764 00000000 0xf2780 00000000 0xf279c 00000000
        }

        deep_blue {
          0xf271c 004c6600
          0xf26f8 c4ccd200 0xf2714 c4ccd200 0xf2720 c4ccd200
          0xf2738 c4ccd200 0xf273c c4ccd200 0xf2740 c4ccd200
          0xf274c c4ccd200 0xf2768 c4ccd200 0xf2774 c4ccd200
          0xf278c c4ccd200 0xf2790 c4ccd200 0xf2794 c4ccd200
          0xf26fc 6e747800 0xf2704 6e747800 0xf2750 6e747800
          0xf2758 6e747800 0xf276c 6e747800
          0xf2700 4a4f5400 0xf2754 4a4f5400
          0xf2708 2a2f3400 0xf270c 2a2f3400 0xf2728 2a2f3400
          0xf2744 2a2f3400 0xf275c 2a2f3400 0xf2760 2a2f3400
          0xf277c 2a2f3400 0xf2798 2a2f3400
          0xf2710 08000800 0xf272c 08000800 0xf2748 08000800
          0xf2764 08000800 0xf2780 08000800 0xf279c 08000800
        }

        night_amber {
            0xf271c 80550000
            0xf26f8 e6d3a300 0xf2714 e6d3a300 0xf2720 e6d3a300
            0xf2738 e6d3a300 0xf273c e6d3a300 0xf2740 e6d3a300
            0xf274c e6d3a300 0xf2768 e6d3a300 0xf2774 e6d3a300
            0xf278c e6d3a300 0xf2790 e6d3a300 0xf2794 e6d3a300
            0xf26fc 7a6a4a00 0xf2704 7a6a4a00 0xf2750 7a6a4a00
            0xf2758 7a6a4a00 0xf276c 7a6a4a00
            0xf2700 564a3600 0xf2754 564a3600
            0xf2708 2e261a00 0xf270c 2e261a00 0xf2728 2e261a00
            0xf2744 2e261a00 0xf275c 2e261a00 0xf2760 2e261a00
            0xf277c 2e261a00 0xf2798 2e261a00
            0xf2710 08000800 0xf272c 08000800 0xf2748 08000800
            0xf2764 08000800 0xf2780 08000800 0xf279c 08000800
        }
        
        graphite {
            0xf271c 4a6a7a00
            0xf26f8 d0d4d800 0xf2714 d0d4d800 0xf2720 d0d4d800
            0xf2738 d0d4d800 0xf273c d0d4d800 0xf2740 d0d4d800
            0xf274c d0d4d800 0xf2768 d0d4d800 0xf2774 d0d4d800
            0xf278c d0d4d800 0xf2790 d0d4d800 0xf2794 d0d4d800
            0xf26fc 7a7f8400 0xf2704 7a7f8400 0xf2750 7a7f8400
            0xf2758 7a7f8400 0xf276c 7a7f8400
            0xf2700 565a5e00 0xf2754 565a5e00
            0xf2708 2c2f3300 0xf270c 2c2f3300 0xf2728 2c2f3300
            0xf2744 2c2f3300 0xf275c 2c2f3300 0xf2760 2c2f3300
            0xf277c 2c2f3300 0xf2798 2c2f3300
            0xf2710 08000800 0xf272c 08000800 0xf2748 08000800
            0xf2764 08000800 0xf2780 08000800 0xf279c 08000800
        }
        
        night_red {
            0xf271c 7a2a2a00
            0xf26f8 e0c8c800 0xf2714 e0c8c800 0xf2720 e0c8c800
            0xf2738 e0c8c800 0xf273c e0c8c800 0xf2740 e0c8c800
            0xf274c e0c8c800 0xf2768 e0c8c800 0xf2774 e0c8c800
            0xf278c e0c8c800 0xf2790 e0c8c800 0xf2794 e0c8c800
            0xf26fc 7a5a5a00 0xf2704 7a5a5a00 0xf2750 7a5a5a00
            0xf2758 7a5a5a00 0xf276c 7a5a5a00
            0xf2700 543a3a00 0xf2754 543a3a00
            0xf2708 2a1c1c00 0xf270c 2a1c1c00 0xf2728 2a1c1c00
            0xf2744 2a1c1c00 0xf275c 2a1c1c00 0xf2760 2a1c1c00
            0xf277c 2a1c1c00 0xf2798 2a1c1c00
            0xf2710 08000800 0xf272c 08000800 0xf2748 08000800
            0xf2764 08000800 0xf2780 08000800 0xf279c 08000800
        }

    }

    # --------------------------------------------------------
    # Apply dispatcher
    # --------------------------------------------------------
    proc apply {name} {
        variable themes

        if {![dict exists $themes $name]} {
            error "unknown theme \"$name\" (use theme::usage)"
        }

        set defs [dict get $themes $name]

        patch::with_guard {
            foreach {addr value} $defs {
                patch::hexstr $addr $value
            }
        }

        return $name
    }

    # Convenience aliases
    proc default {}     { apply default }

    # --------------------------------------------------------
    # Internal helper: extract 4 bytes from bulk read
    # --------------------------------------------------------
    proc _read_u32 {blob base addr} {
        set idx [expr {$addr - $base}]
        set bytes [lrange $blob $idx [expr {$idx + 3}]]
        return [string tolower [format "%02x%02x%02x%02x" \
            [scan [lindex $bytes 0] %x] \
            [scan [lindex $bytes 1] %x] \
            [scan [lindex $bytes 2] %x] \
            [scan [lindex $bytes 3] %x]]]
    }

    # --------------------------------------------------------
    # Detect currently applied theme (full verification)
    # --------------------------------------------------------
    proc current {} {
        variable themes
        variable base_addr
        variable end_addr
        variable entry_len

        set len [expr {$end_addr - $base_addr + $entry_len}]
        set blob [patch::read $base_addr $len]

        foreach {name defs} $themes {
            set ok 1
            foreach {addr expected} $defs {
                set actual [_read_u32 $blob $base_addr $addr]
                if {$actual ne [string tolower $expected]} {
                    set ok 0
                    break
                }
            }
            if {$ok} {
                return $name
            }
        }

        return "custom/unknown"
    }

    # --------------------------------------------------------
    # Usage / help
    # --------------------------------------------------------
    proc usage {} {
        variable themes
    
        set out ""
        append out "\n"
        append out "ResMed AirSense 10 UI Theme Patcher\n"
        append out "---------------------------------\n\n"
        append out "Available themes:\n"
    
        foreach name [lsort [dict keys $themes]] {
            append out "  $name\n"
        }
    
        append out "\n"
        append out "Commands:\n"
        append out "  theme::apply <name>    Apply theme\n"
        append out "  theme::current         Detect current theme\n"
        append out "  theme::usage           Show this help\n"
        append out "\n"
        append out "Example:\n"
        append out "  theme::apply night_toned\n"
        append out "\n"
        append out "Current detected theme:\n"
        append out "  [theme::current]\n"
        append out "\n"
    
        # Try to print (may be suppressed in some shells)
        catch { ::puts $out }
    
        return $out
    }

}

# Uncomment if you want automatic help on load
# theme::usage

