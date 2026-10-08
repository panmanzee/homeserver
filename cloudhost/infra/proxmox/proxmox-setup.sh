#!/bin/sh
# One-time Proxmox setup for customer VMs. Read it before running it; it changes the host.
# Run on the Proxmox host as root. The token secret is written to a root-only file, never printed.
set -eu
TEMPLATE=9000
IMG=/var/lib/vz/template/iso/noble.img     # Ubuntu 24.04 cloud image, checked against Canonical's SHA256SUMS
URL=https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img

# 1. template VM (customer machines are linked clones of it)
[ -f "$IMG" ] || { wget -O "$IMG" "$URL"; }
qm create $TEMPLATE --name ubuntu-2404-template --memory 512 --cores 1 --cpu host --net0 virtio,bridge=vmbr1 \
  --scsihw virtio-scsi-single --serial0 socket --vga serial0 --agent enabled=1 --ostype l26 --onboot 0
qm importdisk $TEMPLATE "$IMG" local-lvm
qm set $TEMPLATE --scsi0 local-lvm:vm-$TEMPLATE-disk-0,discard=on,iothread=1 --ide2 local-lvm:cloudinit \
  --boot order=scsi0 --ciuser ubuntu --nameserver 1.1.1.1
qm template $TEMPLATE

# 2. a least-privilege API identity for the compute service
pveum pool add customers --comment "customer virtual machines"
pveum role add CloudhostVM --privs "VM.Allocate VM.Clone VM.Audit VM.PowerMgmt VM.Console VM.Config.CPU VM.Config.Memory \
VM.Config.Disk VM.Config.Network VM.Config.Cloudinit VM.Config.Options VM.Config.HWType VM.Config.CDROM \
Datastore.AllocateSpace Datastore.Audit SDN.Use Pool.Audit"
pveum user add cloudhost@pve --comment "cloudhost compute service"
pveum user token add cloudhost@pve compute --privsep 1 --output-format json > /root/.pve_compute_token.json
chmod 600 /root/.pve_compute_token.json
# a token with privilege separation gets the intersection of the user's and its own rights: grant both
for p in /pool/customers /vms/$TEMPLATE /storage/local-lvm /sdn/zones/localnetwork; do
  pveum acl modify $p --roles CloudhostVM --users cloudhost@pve --propagate 1
  pveum acl modify $p --roles CloudhostVM --tokens 'cloudhost@pve!compute' --propagate 1
done
echo "done: token saved to /root/.pve_compute_token.json (root only)"
