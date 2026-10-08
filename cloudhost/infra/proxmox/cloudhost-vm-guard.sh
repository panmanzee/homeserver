#!/bin/bash
# Keep the nft set of allowed (tap port . IP) pairs in step with the running customer VMs (ids >= 20000).
set -eu
elems=""
for id in $(qm list | awk '$1>=20000 && $3=="running"{print $1}'); do
  ip=$(qm config "$id" | sed -n 's/^ipconfig0: ip=\([0-9.]*\)\/.*/\1/p')
  [ -n "$ip" ] && elems="$elems\"tap${id}i0\" . $ip, "
done
{
  echo "flush set bridge cloudhost_vm_l2 allowed"
  [ -n "$elems" ] && echo "add element bridge cloudhost_vm_l2 allowed { ${elems%, } }"
} | nft -f -
