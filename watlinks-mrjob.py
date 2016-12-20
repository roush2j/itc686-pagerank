#!/usr/bin/env python2

from __future__ import print_function
import os
import sys
from collections import Counter
import json
from urlparse import urlparse
import hashlib
#
import warc
import boto
from gzipstream import GzipStreamFile
from mrjob.job import MRJob
from mrjob.step import MRStep
import mrjob.protocol as protocols

class WatLinksJob(MRJob):
  
  # Set output protocol to capture only raw (unquoted) values
  # The values in question are keys in our intermediate storage location
  OUTPUT_PROTOCOL = protocols.RawValueProtocol
  
  def steps(self):
    ''' Define the two steps in our pre-processor '''    
    return [
      # 1. download and parse WAT metadata
      MRStep(mapper=self.mapWat, reducer=self.reduceWat),
      # 2. batch together and output to a dedicated S3 bucket
      MRStep(reducer=self.reduceS3)
    ]

  def mapWat(self, _, line):
    ''' Takes partial WARC paths and produces (hostname, {links}) pairs '''
    if self.options.localsource:
      # Stream data from local file
      # this lets us use pre-downloaded *.gz files for testing rather than 
      # hammering the amazon servers.
      fpath = os.path.abspath(os.path.join(self.options.localsource, line))
      print('Loading local file: ' + fpath)
      rawstream = open(fpath, 'rb')
    else:
      # Stream data from common crawl servers
      conn = boto.connect_s3(anon=True, host='s3.amazonaws.com')
      pds = conn.get_bucket('commoncrawl')
      rawstream = boto.s3.key.Key(pds, line)
      
    # iterate through records in warc.wat.gz file
    warcstream = warc.WARCFile(fileobj=GzipStreamFile(rawstream))
    for i, record in enumerate(warcstream):
      if record['Content-Type'] == 'application/json':
        payload = record.payload.read()
        jsonPayload = json.loads(payload)
        hostlinks = self.watHostLinks(jsonPayload)
        if hostlinks: yield hostlinks
      if self.options.localsource and i % 10000 == 0: 
        print('Record %5dk' % (i/1000))
      self.increment_counter('commoncrawl', 'processed_records', 1)
    rawstream.close()
      
  def watHostLinks(self, jsonPayload):
    ''' Takes a JSON WARC.WAT payload and extracts (host, {links}) tuple '''
    envelope = jsonPayload['Envelope']
    meta = envelope['WARC-Header-Metadata']
    if meta['Content-Type'] != 'application/http; msgtype=response': return None
    srchost = parseHost(meta['WARC-Target-URI'])
    if srchost == None: return None
    respmeta = envelope['Payload-Metadata']['HTTP-Response-Metadata']
    if respmeta['Response-Message']['Status'] != '200': return None
    if respmeta['Headers'].get('Content-Type') != 'text/html': return None
    alinks = respmeta['HTML-Metadata'].get('Links', [])
    hlinks = respmeta['HTML-Metadata'].get('Head', {}).get('Link', [])
    linkcounts = Counter()
    for link in alinks + hlinks:
      u = link.get('url')
      if u == None: continue
      tgthost = parseHost(u)
      if tgthost == None or tgthost == srchost: continue
      linkcounts[tgthost] += 1
    return (srchost, linkcounts)

  def reduceWat(self, host, linkmaps):
    ''' Takes a (host, [{links}, {links}, ...]) tuple and merge the link maps '''
    linkcounts = Counter()
    for lm in linkmaps:
      linkcounts.update(lm)
    if len(linkcounts) > 0: yield (hash12(host), (host, linkcounts))
    
  def reduceS3(self, hosthash, hostlinks):
    ''' Takes a  list of [host, [{links}, {links}, ...]] tuples and store into S3 bucket '''
    # we invoke mrjob's protocol code directly to serialize host+links data
    serde = protocols.JSONProtocol()
    content = '\n'.join(serde.write(h, lm) for (h,lm) in hostlinks)
    keypath = 'linkmap/' + hosthash
    if self.options.localdest:
      # Stream output to local file
      fpath = os.path.abspath(os.path.join(self.options.localdest, keypath))
      with open(fpath, 'w') as outfile:
        outfile.write(content)
    else:
      # Stream data to dedicated S3 bucket
      conn = boto.connect_s3(anon=True, host='s3.us-east-2.amazonaws.com')
      pds = conn.get_bucket('jroush-pagerank')
      upload = boto.s3.key.Key(pds, keypath)
      upload.set_contents_from_string(content)
      upload.close()
    yield (None, keypath)      
    
  def configure_options(self):
    super(WatLinksJob, self).configure_options()
    # define a command-line option for specifying local data path.
    self.add_passthrough_option('-s', '--localsource', action='store', default=None,
      help='Specify a local path prefix to obtain data instead of downloading from the S3 bucket.')
    self.add_passthrough_option('-d', '--localdest', action='store', default=None,
      help='Specify a local path prefix to store output instead of uploading to the S3 bucket.')
    
# Parse host name out of a url
def parseHost(urlstr):
  ''' Parse a URL and return the hostname '''
  try:
    url = urlparse(urlstr)
    if url.hostname == None: return None
    else: return url.hostname
  except Exception as e:
    if self.options.localdest: print(e, file=sys.stderr)
    return None

# 12-bit hash of a string, returned as 3 hex characters
def hash12(s):
    m = hashlib.md5()
    m.update(s.encode('utf-8'))
    return m.hexdigest()[:3]

if __name__ == '__main__':
  # LOL hack to resolve local path string before we get sucked into the labrinth
  # of processing mrjob options and start switching the local directory around.
  for i in range(1, len(sys.argv) - 1):
    if sys.argv[i] == '-s' or sys.argv[i] == '--localsource':
      sys.argv[i+1] = os.path.abspath(sys.argv[i+1])
    if sys.argv[i] == '-d' or sys.argv[i] == '--localdest':
      sys.argv[i+1] = os.path.abspath(sys.argv[i+1])
  # run the job
  WatLinksJob.run()
