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
class SKT_T1Tyrant(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.piece_availabilities = dict() # same as for standard
        self.optimistic_unchoked_peer = None # same as for standard
        # peer i estimates u_i,j a minimum upload capacity needed to give to peer j in order for j to unchoke i
        self.min_upload_needed = dict() 
        # peer i estimates d_i,j an estimated download rate it can get from neighbors
        self.possible_download_rates = dict()
        # store frequencies of being unchoked by another agent in last rounds
        self.agents_unchoked_us_recently = dict()
     
    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects 

        This will be called after update_pieces() with the most recent state.
        """
        needed = lambda i: self.pieces[i] < self.conf.blocks_per_piece
        needed_pieces = filter(needed, range(len(self.pieces)))
        np_set = set(needed_pieces)  # sets support fast intersection ops.


        logging.debug("%s here: still need pieces %s" % (
            self.id, needed_pieces))

        logging.debug("%s still here. Here are some peers:" % self.id)
        for p in peers:
            logging.debug("id: %s, available pieces: %s" % (p.id, p.available_pieces))

        logging.debug("And look, I have my entire history available too:")
        logging.debug("look at the AgentHistory class in history.py for details")
        logging.debug(str(history))

        requests = []   # We'll put all the things we want here
        # Symmetry breaking is good...
        random.shuffle(needed_pieces)
        
        # Sort peers by id.  This is probably not a useful sort, but other 
        # sorts might be useful

        # loop through every piece you need
        for needed in needed_pieces:
            # find out which peers have each piece by looping through the piece availabilities of peers
            peers_with_piece = filter(lambda peer: needed in peer.available_pieces, peers)
            # store number of peers with piece in dictionary
            self.piece_availabilities[needed] = len(peers_with_piece)

        # request pieces from all peers, up to self.max_requests from each
        # use rarest-first strategy for requesting pieces from peers
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)
            n = min(self.max_requests, len(isect))
            # sort this based on the pieces in your piece availability dictionary
            sorted_by_rarest = sorted(isect, key=lambda piece: self.piece_availabilities[piece])

            if sorted_by_rarest is None:
                print "No request; no peers have our needed pieces"
                return []

            # This would be the place to try fancier piece-requesting strategies
            # to avoid getting the same thing from multiple peers at a time.

            # take the top n pieces from your dictionary
            for piece_id in sorted_by_rarest[:n]:
                # aha! The peer has this piece! Request it.
                # which part of the piece do we need next?
                # (must get the next-needed blocks in order)
                start_block = self.pieces[piece_id]
                r = Request(self.id, peer.id, piece_id, start_block)
                requests.append(r)

        return requests

    def uploads(self, requests, peers, history):
        """
        requests -- a list of the requests for this peer for this round
        peers -- available info about all the peers
        history -- history for all previous rounds

        returns: list of Upload objects.

        In each round, this will be called after requests().
        """

        round = history.current_round()
        logging.debug("%s again.  It's round %d." % (
            self.id, round))

        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course) has a list of Download objects for each Download to this peer in the previous round.

        requesters_ids = set(map(lambda request: request.requester_id, requests))
        peers_to_unchoke = set()
        peer_ids = map(lambda peer: peer.id, peers)
        # if first round, give unchoke spot to random agent. if later round, give to highest upload bandwith to us
        if round == 0:
            for peer in peers:
                # set up default values for u_ij (minimum upload capacity to give someone for them to unchoke us)
                self.min_upload_needed = self.up_bw/4

                # set up default values for d_ij (i's expected download rate if unchoked by j) 
                self.possible_download_rates = self.up_bw/4
            # randomly pick 4 users requesting pieces from us, and give each of them equal bandwidth
            chosen_peer_ids = random.sample(requesters_ids, 4)
            peers_to_unchoke = chosen_peer_ids
        
        # if later round, use unchoking algorithm (p. 121 of book)
        else:
            # don't upload if you don't receive requests
            # if requests == []:
                # return []

            # keep track of who unchoked us in the past rounds
            unchoked_us_current_round = dict()
            for download in history.downloads[-1]:
                if download.from_id not in unchoked_us_current_round:
                    agents_unchoked_us_recently[download.from_id] += 1
                    unchoked_us_current_round[download.from_id] = 1
            for p in peer_ids:
                # if they did not unchoke us in this round, set to 0 in dictionary
                if p not in unchoked_us_current_round:
                    agents_unchoked_us_recently[p] = 0


            # determine who to unchoke (p.121 of book)
            gamma = 0.10
            r = 3 # num periods
            alpha = 0.20
            estimate_possible_download_rates(self, peers, history, gamma, r, alpha)
            # order peers by decreasing ratio d_ij/u_ij and unchoke top peers for which the sum of their minimum upload capacities < my bandwidth (cap)
            peers_sorted = requesters_ids.sort(key=lambda p: possible_download_rates[p]/min_upload_needed[p], reverse=True)
            # TODO use the dictionary of agents who unchoked us current round to figure out how to use R to estimate_possible_download_rates
            # TODO need to set this, while loop to keep adding the top peers as long as the sum of their min_upload_needed is under capacity (up bw)
            peers_to_unchoke = top_downloads[-3:]

        # Optimistic unchoking every 3 rounds
        if round % 3 == 0 and len(requesters_ids) > len(peers_to_unchoke):
            # randomly choose a person from requesters_ids
            # make sure that person is not someone you're already unchoking
            self.optimistic_unchoked_peer = random.choice(requesters_ids)
            while self.optimistic_unchoked_peer in peers_to_unchoke:
                self.optimistic_unchoked_peer = random.choice(requesters_ids)

        # if we have spots left
        if(len(peers_to_unchoke) < 4):
            peers_to_unchoke.append(self.optimistic_unchoked_peer)
        
        # allocate bandwidth
        bws = even_split(self.up_bw, len(peers_to_unchoke))
        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(peers_to_unchoke, bws)]

        return uploads

    def estimate_possible_download_rates(self, peers, history, gamma, r, alpha):
        peer_ids = map(lambda peer: peer.id, peers)
        agents_we_downloaded_from = set()
        total_downloads_from_peer = dict()
        current_round = history.current_round()
        # might need to use fromKeys to initialize the above to be 0s
        for peer in possible_download_rates:
            for download in history.downloads[-1]:
                # if we have downloaded from peer in the last round (most recent and accurate)
                if download.from_id in agents_we_downloaded_from:
                    agents_we_downloaded_from.add(download.from_id) # add them to set
                    # calculate total download number of blocks they gave us
                    total_downloads_from_peer[peer] += download.blocks
                
                # if we have never downloaded from peer before (they have not unchoked us)
                else:
                    self.min_upload_needed[peer] *= (1+alpha)
                    # assume download rate provided to others = download rate they would give us
                    # go through all their peers to see how much they have downloaded from others
                    for p in peers:
                        # total available pieces / number of rounds
                        p.available_pieces / current_round