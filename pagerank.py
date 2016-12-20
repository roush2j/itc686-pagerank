#!/usr/bin/env python2

from __future__ import print_function
import os
import sys
import json
import hashlib
#
import boto
from mrjob.job import MRJob
from mrjob.step import MRStep
import mrjob.protocol as protocols

class PagerankJob(MRJob):
  
  def steps(self):
    ''' Define the step in our pagerank MR '''    
    if not self.options.damp:
      return [ MRStep(mapper=self.mapTotals, reducer=self.reduceTotals) ]
    else:
      return [ MRStep(mapper=self.mapRanks, reducer=self.reduceRanks),
              MRStep(reducer=self.reduceS3) ]
    
  def hostGroupIter(self, hostgroup):
    ''' Create an iterator over the pages in a host group '''
    N = int(self.options.iteration)
    linkpath = 'linkmap/' + hostgroup
    rankpath = 'rank/' + str(N - 1) + '/' + hostgroup
    linkstream, rankstream = None, None
    if self.options.localsource:
      # Stream data from local file
      linkpath = os.path.abspath(os.path.join(self.options.localsource, linkpath))
      linkstream = open(linkpath, 'rb')
      if N > 1: 
        rankpath = os.path.abspath(os.path.join(self.options.localsource, rankpath))
        rankstream = open(rankpath, 'rb')
    else:
      # Stream data from S3 bucket
      conn = boto.connect_s3(anon=True, host='s3.us-east-2.amazonaws.com')
      pds = conn.get_bucket('jroush-pagerank')      
      linkkey = boto.s3.key.Key(pds, linkpath)
      linkstream = linkkey.open_read()
      if N > 1: 
        rankkey = boto.s3.key.Key(pds, rankpath)
        rankstream = rankkey.open_read()
        
    # build a map of ranking from previous iteration
    if N > 1:
      rankmap = {}
      for page in rankstream.readlines():
        host, R = page.split('\t')
        rankmap['host'] = float(R)
      rankstream.close()
       
    # iterate through pages in group
    serde = protocols.JSONProtocol()
    for page in linkstream.readlines():
      # deserialize link data
      host, linkmap = serde.read(page)
      # get ranking from previous iteration
      if N > 1: R = rankmap.get(host, 1.0)
      else: R = 1.0
      # yield
      yield (host, R, linkmap)
    linkstream.close()

  def mapTotals(self, _, hostgroup):
    ''' Takes partial path to host group and maps to the partial sums of page count and deadpage total '''
    total = 0
    dead = 0.0
    for host, R, linkmap in self.hostGroupIter(hostgroup):
      # count number of outgoing links
      if len(linkmap) == 0: dead += R
      total += 1
      self.increment_counter('pagerank', 'processed_groups', 1)
    yield (None, (total, dead)) 

  def reduceTotals(self, _, stats):
    ''' Takes a list of partial totals, summarizes, and store into S3 bucket '''
    total = 0
    dead = 0.0
    for ptotal, pdead in stats:
      total += ptotal
      dead += pdead
    
    # store output
    N = int(self.options.iteration)
    rankpath = 'rank/' + str(N) + '/totals'
    content = str(total) + '\t' + str(dead)
    if self.options.localdest:
      # Stream output to local file
      fpath = os.path.abspath(os.path.join(self.options.localdest, rankpath))
      fdir = os.path.dirname(fpath)
      if not os.path.exists(fdir): os.makedirs(fdir)
      with open(fpath, 'w') as outfile:
        outfile.write(content)
    else:
      # Stream data to dedicated S3 bucket
      conn = boto.connect_s3(anon=True, host='s3.us-east-2.amazonaws.com')
      pds = conn.get_bucket('jroush-pagerank')
      upload = boto.s3.key.Key(pds, rankpath)
      upload.set_contents_from_string(content)
      upload.close()
    yield (None, (total, dead)) 

  def mapRanks(self, _, hostgroup):    
    ''' Takes partial path to host group and maps to contribution to each dest link '''
    N = int(self.options.iteration)
    
    # iterate through pages in group and sum up partial ranks
    for host, R, linkmap in self.hostGroupIter(hostgroup):
      # calculate partial rank for each outgoing link
      norm = R / len(linkmap)
      for tgt,cnt in linkmap.items():
          yield (tgt, norm * cnt)
      self.increment_counter('pagerank', 'processed_groups', 1)
              
  def reduceRanks(self, host, pRanks):
    ''' Take a list of partial ranks and sum them to a full rank '''
    
    # read totals from first pass
    N = int(self.options.iteration)
    rankpath = 'rank/' + str(N) + '/totals'
    if self.options.localdest:
      # Stream output from local file
      fpath = os.path.abspath(os.path.join(self.options.localdest, rankpath))
      fdir = os.path.dirname(fpath)
      if not os.path.exists(fdir): os.makedirs(fdir)
      with open(fpath, 'r') as outfile:
        total, dead = outfile.readline().split('\t')
    else:
      # Stream data from dedicated S3 bucket
      conn = boto.connect_s3(anon=True, host='s3.us-east-2.amazonaws.com')
      pds = conn.get_bucket('jroush-pagerank')
      upload = boto.s3.key.Key(pds, rankpath)
      total, dead = upload.get_contents_as_string().split('\t')
      upload.close()
    total = int(total)
    dead = float(dead)
      
    # read damping factor
    Q = float(self.options.damp)
    
    # compute full rank for page
    fullrank = (1-Q + Q*dead) + Q * sum(pRanks)
    yield (hash12(host), (host, fullrank))
    
  def reduceS3(self, hosthash, hostranks):
    ''' Takes a  list of [host, rank] tuples and store into S3 bucket '''
    # we invoke mrjob's protocol code directly to serialize host+links data
    N = int(self.options.iteration)
    serde = protocols.JSONProtocol()
    content = '\n'.join(serde.write(h, r) for (h,r) in hostranks)
    hostgroup = hosthash[0] + '/' + hosthash[1:3]
    keypath = 'rank/' + str(N) + '/' + hostgroup
    if self.options.localdest:
      # Stream output to local file
      fpath = os.path.abspath(os.path.join(self.options.localdest, keypath))
      fdir = os.path.dirname(fpath)
      if not os.path.exists(fdir): os.makedirs(fdir)
      with open(fpath, 'w') as outfile:
        outfile.write(content)
    else:
      # Stream data to dedicated S3 bucket
      conn = boto.connect_s3(anon=True, host='s3.us-east-2.amazonaws.com')
      pds = conn.get_bucket('jroush-pagerank')
      upload = boto.s3.key.Key(pds, keypath)
      upload.set_contents_from_string(content)
      upload.close()
    
  def configure_options(self):
    super(PagerankJob, self).configure_options()
    # define a command-line option for specifying local data path and iteration number.
    self.add_passthrough_option('-s', '--localsource', action='store', default=None,
      help='Specify a local path prefix to obtain data instead of downloading from the S3 bucket.')
    self.add_passthrough_option('-d', '--localdest', action='store', default=None,
      help='Specify a local path prefix to store output instead of uploading to the S3 bucket.')
    self.add_passthrough_option('-I', '--iteration', action='store', type='int', default=None,
      help='Specify the iteration number.')
    self.add_passthrough_option('-D', '--damp', action='store', type='float', default=None,
      help='Specify the damping factor.')
      
# 12-bit hash of a string, returned as 3 hex characters
def hash12(s):
    m = hashlib.md5()
    m.update(s.encode('utf-8'))
    return m.hexdigest()[:3]

if __name__ == '__main__':
  # LOL hack to resolve local path string before we get sucked into the labrinth
  # of processing mrjob options and start switching the local directory around.
  foundIter, foundDamp = False, False
  for i in range(1, len(sys.argv) - 1):
    if sys.argv[i] == '-s' or sys.argv[i] == '--localsource':
      sys.argv[i+1] = os.path.abspath(sys.argv[i+1])
    if sys.argv[i] == '-d' or sys.argv[i] == '--localdest':
      sys.argv[i+1] = os.path.abspath(sys.argv[i+1])
    if sys.argv[i] == '-I' or sys.argv[i] == '--iteration':
      foundIter = True
  if not foundIter: 
    print("An iteration number must be provided, e.g. --iteration 5", file=sys.stderr)
    exit(12)
  # run the job
  PagerankJob.run()
