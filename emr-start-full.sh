#!/bin/sh

# This script spins up an EMR cluster with 250 servers for a full run

# NOTE: this requires the AWS CLI package
#       you should be running this from *inside* a virtualenv with awscli installed

aws emr create-cluster \
    --name 'FullCluster' \
    --log-uri 's3n://jroush-pagerank/logs/' \
    --region us-east-1 \
    --bootstrap-action Path="s3://jroush-pagerank/emr-bootstrap.sh" \
    --applications Name=Ganglia Name=Hadoop Name=Hive Name=Hue Name=Mahout Name=Pig Name=Tez \
    --ec2-attributes '{"KeyName":"jroush@jroush-dennis","InstanceProfile":"EMR_EC2_DefaultRole","SubnetId":"subnet-8f0d22d6","EmrManagedSlaveSecurityGroup":"sg-b72b18ca","EmrManagedMasterSecurityGroup":"sg-ba2b18c7"}' \
    --service-role EMR_DefaultRole \
    --enable-debugging \
    --release-label emr-5.2.0 \
    --instance-groups '[{"InstanceCount":240,"InstanceGroupType":"CORE","InstanceType":"m1.medium","Name":"Core Instance Group"},{"InstanceCount":1,"InstanceGroupType":"MASTER","InstanceType":"m1.xlarge","Name":"Master Instance Group"}]' \
    --scale-down-behavior TERMINATE_AT_INSTANCE_HOUR \
    