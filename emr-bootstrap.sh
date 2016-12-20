#!/bin/bash

# This script installs dependencies on individual EMR nodes
# It should be uploaded to S3, where it is referenced 
# by the emr-start-* scripts.

sudo yum --releasever=2014.09 install -y python27 python27-devel gcc-c++
sudo easy_install-2.7 pip
sudo /usr/local/bin/pip2.7 install boto mrjob simplejson warc
sudo /usr/local/bin/pip2.7 install https://github.com/commoncrawl/gzipstream/archive/master.zip