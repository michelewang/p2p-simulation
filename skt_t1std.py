#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers 
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer
from collections import defaultdict
from random import sample 

class SKT_T1Std(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.piece_availabilities = dict()
        self.optimistic_unchoked_peer = None
    
    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects 

        This will be called after update_pieces() with the most recent state.
        """
        need_list = []
        for i in range(len(self.pieces)):
            if self.pieces[i] < self.conf.blocks_per_piece:
                need_list.append(i)
        need_set = set(need_list)

        logging.debug("%s here: still need pieces %s" % (
            self.id, need_list))
        logging.debug("%s still here. Here are some peers:" % self.id)
        for p in peers:
            logging.debug("id: %s, available pieces: %s" % (p.id, p.available_pieces))
        logging.debug("And look, I have my entire history available too:")
        logging.debug(str(history))

        requests = []

        # Store number of peers with our needed pieces in dictionary
        for needed in need_list:
            peers_with_piece = filter(lambda peer: needed in peer.available_pieces, peers)
            self.piece_availabilities[needed] = len(peers_with_piece)

        # Request pieces from all peers, up to self.max_requests from each
        # Use rarest-first strategy for requesting pieces from peers
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(need_set)
            n = min(self.max_requests, len(isect))
            sorted_by_rarest = sorted(isect, key=lambda piece: self.piece_availabilities[piece])

            if sorted_by_rarest is None:
                logging.debug("No request; no peers have our needed pieces")
                return []

            # This would be the place to try fancier piece-requesting strategies
            # to avoid getting the same thing from multiple peers at a time.

            # Take the top n pieces from the dictionary and get the next-needed blocks in order
            for piece_id in sorted_by_rarest[:n]:
                start_block = self.pieces[piece_id]
                r = Request(self.id, peer.id, piece_id, start_block)
                requests.append(r)

        logging.debug("Requests from {}: {}".format(self.id, requests))
        return requests

    def uploads(self, requests, peers, history):
        """
        requests -- a list of the requests for this peer for this round
        peers -- available info about all the peers
        history -- history for all previous rounds

        returns: list of Upload objects which specify how much of its upload bandwidth to allocate
to any given peer. 
        In each round, this will be called after requests().
        
        """

        round = history.current_round()
        logging.debug("%s again.  It's round %d." % (
            self.id, round))

        # Don't upload if you don't receive requests
        if not requests:
            return []

        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course) has a list of Download objects for each Download to this peer in the previous round.

        requesters_ids = set(map(lambda request: request.requester_id, requests))

        # If first round, give unchoke spot to random agent. If later round, give to agent who gave us highest bandwidth
        if round == 0:
            # Randomly pick 4 users requesting pieces from us, and give each of them equal bandwidth
            chosen_peer_ids = random.sample(requesters_ids, 4)
            peers_to_unchoke = chosen_peer_ids
        else:
            # Pick the top 3 requesters who gave us the highest upload bandwidth in the past period
            downloads = history.downloads[-1]
            down_bw = defaultdict(int)
            for download in downloads:
                if download.from_id in requesters_ids:
                    down_bw[download.from_id] += download.blocks
            top_downloads = sorted(requesters_ids, key=lambda x: down_bw[x], reverse=True)
            peers_to_unchoke = top_downloads[-3:]

        # Optimistic unchoking every 3 rounds: randomly choose an agent who isn't already in peers_to_unchoke
        if round % 3 == 0 and len(requesters_ids) > len(peers_to_unchoke):
            self.optimistic_unchoked_peer = random.choice(requesters_ids)
            while self.optimistic_unchoked_peer in peers_to_unchoke:
                self.optimistic_unchoked_peer = random.choice(requesters_ids)

        # If we have spots left, add the peer from optimistic unchoking
        if len(peers_to_unchoke) < 4:
            peers_to_unchoke.append(self.optimistic_unchoked_peer)

        bws = even_split(self.up_bw, len(peers_to_unchoke))
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(peers_to_unchoke, bws)]
            
        return uploads
