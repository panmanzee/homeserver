    ${name} {
        version = 2
        remote_addrs = ${aws_outside}
        proposals = aes256-sha256-modp2048
        local_addrs = %any
        dpd_delay = 10s
        rekey_time = 8h
${ike_if}
        local {
            auth = psk
            id = ${local_id}
        }
        remote {
            auth = psk
            id = ${aws_outside}
        }
        children {
            ${name} {
                local_ts = 0.0.0.0/0
                remote_ts = 0.0.0.0/0
                esp_proposals = aes256-sha256-modp2048
                start_action = start
                dpd_action = restart
                rekey_time = 1h
${child_if}
            }
        }
    }
