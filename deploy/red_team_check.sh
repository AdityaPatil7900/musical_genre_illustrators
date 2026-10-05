#!/bin/bash
KEY="/d/CS553/student-admin_key"
MACHINE=paffenroth-23.dyn.wpi.edu
MY_GROUP=12

for i in $(seq 1 21); do
  if [ "$i" -eq "$MY_GROUP" ]; then continue; fi
  port=$((22000 + i))
  echo "=== Trying group $i (port $port) at $(date) ==="
  ssh -i "$KEY" -p "$port" -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
      student-admin@${MACHINE} "echo VULNERABLE on group $i; hostname; date"
  echo ""
done
