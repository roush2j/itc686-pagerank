#!/usr/bin/sh

# Access credentials are held in $AWS_ACCESS_KEY_ID and $AWS_SECRET_ACCESS_KEY
source ./emr-keys.sh

# run job
# Arg1 is relative path to input file, e.g. 'crawl-data/CC-MAIN-2016-36/wat.paths'
# Arg2 is clusterID, e.g. 'j-HDE89KVDCFET'
./watlinks-mrjob.py "$1" \
    --output-dir "s3://jroush-pagerank/out" \
    --region 'us-east-1' \
    --cluster-id "$2" \
    -r emr \
