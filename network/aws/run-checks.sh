#!/bin/bash
# fmt, init, validate, plan, then apply+destroy against LocalStack on :4567
cd "$(dirname "$0")/terraform" || exit 1
export TF_IN_AUTOMATION=1
step() { echo; echo "=== $* ==="; }
fail=0

step "versions"
terraform version
date

step "terraform fmt -check"
terraform fmt -check -recursive || fail=1

step "terraform init"
terraform init -input=false || exit 1

step "terraform validate"
terraform validate || fail=1

step "start localstack on 4567"
# WSL docker config points at a windows credential helper that is not there
export DOCKER_CONFIG=$(mktemp -d)
echo '{}' > "$DOCKER_CONFIG/config.json"
docker rm -f ls-aws >/dev/null 2>&1
docker run -d --name ls-aws -p 4567:4566 localstack/localstack:3.8
for i in $(seq 1 60); do
  curl -s localhost:4567/_localstack/health | grep -q '"ec2"' && break
  sleep 2
done
curl -s localhost:4567/_localstack/health | head -c 400; echo

step "plan (use_localstack=true, everything incl. VPN connection)"
terraform plan -input=false -var-file=localstack.tfvars -out=full.tfplan -no-color | tail -40
echo "plan exit: ${PIPESTATUS[0]}"

step "apply, VPN connection included"
terraform apply -input=false -auto-approve -var-file=localstack.tfvars -no-color 2>&1 | tail -60
echo "apply(full) exit: ${PIPESTATUS[0]}"

step "state after first apply"
terraform state list

step "destroy"
terraform destroy -input=false -auto-approve -var-file=localstack.tfvars -no-color 2>&1 | tail -15
echo "destroy exit: ${PIPESTATUS[0]}"

step "second apply, excluding budget + route propagation (501 on localstack)"
terraform apply -input=false -auto-approve -var-file=localstack.tfvars \
  -var create_route_propagation=false -var create_budget=false -no-color 2>&1 | tail -40
echo "apply(reduced) exit: ${PIPESTATUS[0]}"
terraform state list

step "render homelab config from terraform output -json"
terraform output -json > /tmp/tf-out.json
python3 ../homelab-side/render.py /tmp/tf-out.json --local-id 198.51.100.7 --out /tmp/render-out
grep -E "neighbor .* remote-as|router bgp" /tmp/render-out/frr.conf
grep -E "remote_addrs|proposals" /tmp/render-out/swanctl.conf
rm -rf /tmp/tf-out.json /tmp/render-out

step "destroy reduced"
terraform destroy -input=false -auto-approve -var-file=localstack.tfvars \
  -var create_route_propagation=false -var create_budget=false -no-color 2>&1 | tail -8
echo "destroy(reduced) exit: ${PIPESTATUS[0]}"

step "cleanup"
docker rm -f ls-aws
rm -f full.tfplan terraform.tfstate*
echo "fmt/validate fail flag: $fail"
exit $fail
