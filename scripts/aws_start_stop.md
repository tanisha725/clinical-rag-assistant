# Starting / stopping the AWS instance

Instance ID: `i-0d089f670fd7445e6` | Region: `ap-southeast-2` | Security group: `sg-04e7334c88153cf0d`

## To start it again before using the app

**[MAC]**
```bash
aws ec2 start-instances --instance-ids i-0d089f670fd7445e6 --region ap-southeast-2
aws ec2 wait instance-running --instance-ids i-0d089f670fd7445e6 --region ap-southeast-2
aws ec2 describe-instances --instance-ids i-0d089f670fd7445e6 --region ap-southeast-2 \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text
```
The last command prints the new public IP — **it changes every time you stop/start**, so note it down.

Then allow your current IP through the firewall (get it from https://whatismyipaddress.com first):
```bash
aws ec2 authorize-security-group-ingress --group-id sg-04e7334c88153cf0d --protocol tcp --port 22 --cidr YOUR_IP/32 --region ap-southeast-2
aws ec2 authorize-security-group-ingress --group-id sg-04e7334c88153cf0d --protocol tcp --port 7860 --cidr YOUR_IP/32 --region ap-southeast-2
```

**One-time step, next start only:** the running containers need to be recreated once with
the new auto-restart setting (added after the instance was last stopped, so it hasn't been
applied on the box yet). Copy the updated compose file up, then recreate:
```bash
scp -i ~/.ssh/idt-project-key.pem docker-compose.aws-free-tier.yml ubuntu@<new-ip>:~/idt_project/
ssh -i ~/.ssh/idt-project-key.pem ubuntu@<new-ip> \
  "cd ~/idt_project && sudo docker compose -f docker-compose.aws-free-tier.yml up -d"
```
After this one-time step, the containers restart themselves automatically every time the
instance starts — you won't need to SSH in again just to bring the app back up.

Give it ~30-60 seconds after "running" before the app answers at `http://<new-ip>:7860`.

## To stop it when you're done for the day

**[MAC]**
```bash
aws ec2 stop-instances --instance-ids i-0d089f670fd7445e6 --region ap-southeast-2
```
Everything (Docker images, the knowledge base, the qwen model) stays on disk — starting it again does not require re-running any setup.

## Why the IP changes and the firewall step is needed

AWS assigns a new public IP each time a stopped instance starts again (unless you pay for a
static Elastic IP, which isn't necessary for a free-tier class project). The security group
only allows traffic from a specific IP address for safety, so both "my IP" and "the
instance's IP" can change between sessions — that's normal, not a bug.
