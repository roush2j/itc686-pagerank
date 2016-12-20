#!/usr/bin/sh

# Access credentials are held in $AWS_ACCESS_KEY_ID and $AWS_SECRET_ACCESS_KEY
source ./emr-keys.sh

# run job
# Arg1 is relative path to input file, e.g. 'crawl-data/CC-MAIN-2016-36/wat.paths'
# Arg2 is clusterID, e.g. 'j-HDE89KVDCFET'
./watlinks-mrjob.py "$1" \
    --region 'us-east-1' \
    --cluster-id "$2" \
    -r emr \
#    --ec2-key-pair 'jroush@jroush-dennis' \
#    --ec2-key-pair-file '/home/jroush/.ssh/id_rsa' \

# Note that, in order to SSH into the EMR servers we must enable SSH connections
# explicitly in their security policies.