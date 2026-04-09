# ============================================================
# ResMed AirSense 10 UI Theme Patcher
# ============================================================

namespace eval theme {

    # --------------------------------------------------------
    # Address layout (per-version)
    # --------------------------------------------------------
    variable entry_len 4
    variable cdx_ver ""
    variable base_addr
    variable end_addr
    variable groups

    # --------------------------------------------------------
    # Detect CDX version and set palette addresses
    # --------------------------------------------------------
    proc _detect_version {} {
        variable cdx_ver
        variable base_addr
        variable end_addr
        variable groups

        set cdx_ver [patch::read_string 0x40000 11 -nul]

        switch -exact -- $cdx_ver {
            SX567-0401 - SX567-0306 {
                set base_addr 0xf26f8
                set end_addr  0xf279c
                array set groups {
                    selected {0xf271c}
                    whites {
                        0xf26f8 0xf2714 0xf2720
                        0xf2738 0xf273c 0xf2740
                        0xf274c 0xf2768 0xf2774
                        0xf278c 0xf2790 0xf2794
                    }
                    bright {
                        0xf26fc 0xf2704 0xf2750
                        0xf2758 0xf276c
                    }
                    mid {
                        0xf2700 0xf2754
                    }
                    low {
                        0xf2708 0xf270c 0xf2728
                        0xf2744 0xf275c 0xf2760
                        0xf277c 0xf2798
                    }
                    black {
                        0xf2710 0xf272c 0xf2748
                        0xf2764 0xf2780 0xf279c
                    }
                }
            }
            SX567-0402 {
                set base_addr 0xf2970
                set end_addr  0xf2a14
                array set groups {
                    selected {0xf2994}
                    whites {
                        0xf2970 0xf298c 0xf2998
                        0xf29b0 0xf29b4 0xf29b8
                        0xf29c4 0xf29e0 0xf29ec
                        0xf2a04 0xf2a08 0xf2a0c
                    }
                    bright {
                        0xf2974 0xf297c 0xf29c8
                        0xf29d0 0xf29e4
                    }
                    mid {
                        0xf2978 0xf29cc
                    }
                    low {
                        0xf2980 0xf2984 0xf29a0
                        0xf29bc 0xf29d4 0xf29d8
                        0xf29f4 0xf2a10
                    }
                    black {
                        0xf2988 0xf29a4 0xf29c0
                        0xf29dc 0xf29f8 0xf2a14
                    }
                }
            }
            default {
                error "theme: unsupported CDX version \"$cdx_ver\""
            }
        }
    }

    proc _ensure_version {} {
        variable cdx_ver
        if {$cdx_ver eq ""} { _detect_version }
    }


    # --------------------------------------------------------
    # Theme definitions
    # --------------------------------------------------------

    variable themes_uncompensated {
        default {
            selected 0099cc00
            whites   ffffff00
            bright   96969600
            mid      64646400
            low      40404000
            black    00000000
        }

        default_low_gamma {
            selected 0082ad00
            whites   e0e0e000
            bright   86868600
            mid      5e5e5e00
            low      40404000
            black    00000000
        }

        default_very_low_gamma {
            selected 00739900
            whites   cccccd00
            bright   78787800
            mid      54545400
            low      3a3a3a00
            black    00000000
        }

        default_ultra_low_gamma {
            selected 00608000
            whites   b6b6b600
            bright   64646400
            mid      44444400
            low      2e2e2e00
            black    00000000
        }

        default_dim {
            selected 00506600
            whites   cccccd00
            bright   6a6a6a00
            mid      4a4a4a00
            low      24242400
            black    00000000
        }

        default_blackout {
            selected 00404f00
            whites   d6d6d600
            bright   5c5c5c00
            mid      3a3a3a00
            low      1c1c1c00
            black    00000000
        }

        asmageddon {
            selected cc330000
            whites   ffbb4400
            bright   96484800
            mid      64323200
            low      40202000
            black    08000800
        }

        asmageddon_dark {
            selected 70180c00
            whites   f3885100
            bright   50282800
            mid      2c161600
            low      11080800
            black    08000800
        }

        night_vision {
            selected 66000000
            whites   e6c0c000
            bright   4a2a2a00
            mid      32181800
            low      160a0a00
            black    00000000
        }

        night_toned {
            selected 00668800
            whites   d8d8d800
            bright   80808000
            mid      58585800
            low      30303000
            black    00000000
        }

        night_dark {
            selected 00557700
            whites   c8c8c800
            bright   78787800
            mid      50505000
            low      28282800
            black    00000000
        }

        deep_blue {
            selected 004c6600
            whites   c4ccd200
            bright   6e747800
            mid      4a4f5400
            low      2a2f3400
            black    08000800
        }

        night_amber {
            selected 80550000
            whites   e6d3a300
            bright   7a6a4a00
            mid      564a3600
            low      2e261a00
            black    08000800
        }

        graphite {
            selected 4a6a7a00
            whites   d0d4d800
            bright   7a7f8400
            mid      565a5e00
            low      2c2f3300
            black    08000800
        }

        graphite_dark {
            selected 36515f00
            whites   d6d6d600
            bright   62676c00
            mid      44484c00
            low      24272b00
            black    08000800
        }

        night_red {
            selected 7a2a2a00
            whites   e0c8c800
            bright   7a5a5a00
            mid      543a3a00
            low      2a1c1c00
            black    08000800
        }

        ember_night {
            selected 66160000
            whites   d8c6c000
            bright   5a403800
            mid      3e2a2400
            low      1f140f00
            black    00000000
        }

        charcoal_light {
            selected 2e3a4000
            whites   b8b8b800
            bright   4a4a4a00
            mid      2f2f2f00
            low      18181800
            black    00000000
        }

        charcoal {
            selected 1e262a00
            whites   8e8e8e00
            bright   2c2c2c00
            mid      1a1a1a00
            low      0c0c0c00
            black    00000000
        }

        charcoal_warm {
            selected 3a2a2400
            whites   b8a8a000
            bright   4a3e3800
            mid      30262200
            low      18120f00
            black    00000000
        }

    }

    variable themes {

        default {
            selected 0099cc00
            whites   ffffff00
            bright   96969600
            mid      64646400
            low      40404000
            black    00000000
        }

        default_low_gamma {
            selected 00828c00
            whites   e4e0d600
            bright   90867100
            mid      685e4b00
            low      48403100
            black    00000000
        }

        default_very_low_gamma {
            selected 00737a00
            whites   d2ccbe00
            bright   82786300
            mid      5d544200
            low      423a2d00
            black    00000000
        }

        default_ultra_low_gamma {
            selected 00606400
            whites   beb6a300
            bright   6e645000
            mid      4c443500
            low      342e2300
            black    00000000
        }

        default_dim {
            selected 00504f00
            whites   d2ccbe00
            bright   746a5600
            mid      534a3a00
            low      29241800
            black    00000000
        }

        default_blackout {
            selected 00404200
            whites   dbd6ca00
            bright   655c4a00
            mid      413a2d00
            low      1f1c1500
            black    00000000
        }

        ember_night {
            selected 75160000
            whites   e2c6a000
            bright   65402a00
            mid      482a1a00
            low      24140b00
            black    00000000
        }

        asmageddon {
            selected cc330000
            whites   ffbb4400
            bright   96484800
            mid      64323200
            low      40202000
            black    08000800
        }

        asmageddon_dark {
            selected 7d180a00
            whites   ff886300
            bright   58281900
            mid      30160f00
            low      12080700
            black    08000800
        }

        night_vision {
            selected 76000000
            whites   f0c09c00
            bright   542a1f00
            mid      3a180f00
            low      1a0a0700
            black    00000000
        }

        night_toned {
            selected 00666700
            whites   ddd8ce00
            bright   8a806c00
            mid      5f584800
            low      342e2400
            black    00000000
        }

        night_dark {
            selected 00555600
            whites   cec8ba00
            bright   82786300
            mid      564f4000
            low      2c281f00
            black    00000000
        }

        deep_blue {
            selected 004c3600
            whites   cdccb700
            bright   78745e00
            mid      534f3f00
            low      302f2500
            black    08000800
        }

        night_amber {
            selected 8c550000
            whites   f0d39000
            bright   896a3a00
            mid      604c2700
            low      34261400
            black    08000800
        }

        graphite {
            selected 506a5d00
            whites   dad4c400
            bright   897f6800
            mid      5f5a4900
            low      312f2500
            black    08000800
        }

        night_red {
            selected 862a2200
            whites   e6c8aa00
            bright   896a4c00
            mid      5e4f3b00
            low      2e1c1600
            black    08000800
        }

        graphite_dark {
            selected 3b515400
            whites   bfb6a800
            bright   6c675300
            mid      4c483a00
            low      27271f00
            black    08000800
        }

        charcoal_light {
            selected 333a3300
            whites   c0b8a000
            bright   534a3a00
            mid      362f2300
            low      1c181200
            black    00000000
        }

        charcoal {
            selected 22261f00
            whites   988e7900
            bright   322c2100
            mid      1e1a1300
            low      0e0c0900
            black    00000000
        }

        charcoal_warm {
            selected 422a1b00
            whites   c2a88d00
            bright   533e2b00
            mid      37261900
            low      1c120b00
            black    00000000
        }
    }



    # --------------------------------------------------------
    # Apply dispatcher
    # --------------------------------------------------------

    proc apply {name} {
        _ensure_version
        variable themes

        if {![dict exists $themes $name]} {
            error "unknown theme \"$name\""
        }

        set theme [dict get $themes $name]

        if {[string match 0x* [lindex $theme 0]]} {
            apply_flat $name
        } else {
            apply_grouped $name
        }
    }

    proc apply_flat {name} {
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


    proc apply_grouped {name} {
        variable themes
        variable groups

        if {![dict exists $themes $name]} {
            error "unknown theme \"$name\""
        }

        set theme [dict get $themes $name]

        patch::with_guard {
            foreach {group color} $theme {
                if {![info exists groups($group)]} {
                    error "unknown color group \"$group\""
                }
                foreach addr $groups($group) {
                    patch::hexstr $addr $color
                }
            }
        }

        return $name
    }



    proc patch_group {group givencolor} {
        _ensure_version
        variable groups

        if {![info exists groups($group)]} {
            error "unknown color group \"$group\""
        }

        patch::with_guard {
            foreach addr $groups($group) {
                patch::hexstr $addr $givencolor
            }
        }

        return $group
    }

    proc patch_groups {group_color_pairs} {
        _ensure_version
        variable groups

        patch::with_guard {
            foreach {group color} $group_color_pairs {
                if {![info exists groups($group)]} {
                    error "unknown color group \"$group\""
                }
                foreach addr $groups($group) {
                    patch::hexstr $addr $color
                }
            }
        }

        return $group_color_pairs
    }

    proc apply_groups {name group_list} {
        variable themes
        variable groups

        if {![dict exists $themes $name]} {
            error "unknown theme \"$name\""
        }

        set defs [dict get $themes $name]

        patch::with_guard {
            foreach group $group_list {
                if {![info exists groups($group)]} {
                    error "unknown color group \"$group\""
                }
                foreach addr $groups($group) {
                    set idx [lsearch -exact $defs $addr]
                    if {$idx >= 0} {
                        patch::hexstr $addr [lindex $defs [expr {$idx + 1}]]
                    }
                }
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
    # Detect currently applied theme
    # --------------------------------------------------------

    proc current {{arg ""}} {
        _ensure_version
        variable themes
        variable groups
        variable base_addr
        variable end_addr
        variable entry_len

        set verbose 0
        if {$arg eq "-v"} {
            set verbose 1
        } elseif {$arg ne ""} {
            error "usage: theme::current ?-v?"
        }

        set len [expr {$end_addr - $base_addr + $entry_len}]
        set blob [patch::read $base_addr $len]

        set current {}

        foreach group [array names groups] {
            set vals {}
            foreach addr $groups($group) {
                lappend vals [_read_u32 $blob $base_addr $addr]
            }
            set uniq [lsort -unique $vals]
            if {[llength $uniq] == 1} {
                dict set current $group [lindex $uniq 0]
            } else {
                dict set current $group mixed
            }
        }

        set detected "custom/unknown"

        foreach {name theme} $themes {
            set ok 1
            foreach {group expected} $theme {
                if {![dict exists $current $group]} {
                    set ok 0
                    break
                }
                if {[dict get $current $group] ne [string tolower $expected]} {
                    set ok 0
                    break
                }
            }
            if {$ok} {
                set detected $name
                break
            }
        }

        if {$verbose} {
            echo "Current theme: $detected"
            echo "Current colors by group:"
            foreach group [lsort [array names groups]] {
                echo [format "  %-9s : %s" $group [dict get $current $group]]
            }
        }

        return $detected
    }



    # --------------------------------------------------------
    # Usage / help
    # --------------------------------------------------------

    proc usage {} {
        _ensure_version
        variable themes
        variable groups
        variable base_addr
        variable end_addr
        variable entry_len

        echo "Commands:"
        echo "  theme::usage"
        echo "      Show this help and current theme state"
        echo ""
        echo "  theme::current \[-v\]"
        echo "      Detect currently applied theme"
        echo ""
        echo "  theme::apply <theme>"
        echo "      Apply full theme by name"
        echo ""
        echo "  theme::apply_groups <theme> <group1> ?group2 ...?"
        echo "      Apply only selected color groups from a theme"
        echo ""
        echo "  theme::patch_group <group> <color>"
        echo "      Patch a single color group with a raw color value"
        echo ""
        echo "  theme::patch_groups { <group> <color> ... }"
        echo "      Patch multiple groups with explicit colors"
        echo ""

        echo "Color groups:"
        foreach group [lsort [array names groups]] {
            echo "  $group"
        }

        echo ""
        echo "Available themes:"
        foreach {name _} $themes {
            echo "  $name"
        }

        echo ""
        echo "Examples:"
        echo "  theme::apply default_blackout"
        echo "  theme::apply_groups night_vision { whites low }"
        echo "  theme::patch_group whites d6d6d600"
        echo "  theme::patch_groups { whites d6d6d600 low 1c1c1c00 }"
    }


}

if {[info level] == 0} {
    theme::usage
} else {
    echo "[info script] loaded."
    echo {    theme::usage for instructions}
}

