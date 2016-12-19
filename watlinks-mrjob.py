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

class WatLinksJob(MRJob):
  
  def steps(self):
    return [
      MRStep(mapper=self.mapWat, reducer=self.reduceWat),
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
      print('Streaming from Amazon S3 bucket: ' + line)
      conn = boto.connect_s3(anon=True)
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
      if i % 10000 == 0: print('Record %5dk' % (i/1000))
      self.increment_counter('commoncrawl', 'processed_records', 1)
      
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
    #conn = boto.connect_s3(anon=True)
    #pds = conn.get_bucket('jroush-pagerank')
    #rawstream = boto.s3.key.Key(pds, hosthash)
    yield hosthash
    
  def configure_options(self):
    super(WatLinksJob, self).configure_options()
    # define a command-line option for specifying local data path.
    self.add_passthrough_option('-s', '--localsource', action='store', default=None,
      help='Specify a local path prefix to obtain data instead of downloading from the S3 bucket.')
    
# Parse host name out of a url
def parseHost(urlstr):
  ''' Parse a URL and return the hostname '''
  try:
    url = urlparse(urlstr)
    if url.hostname == None: return None
    else: return url.hostname
  except Exception as e:
    print(e, file=sys.stderr)
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
  # run the job
  WatLinksJob.run()
