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


class SKT_T1Tyrant(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.piece_availabilities = dict()
        self.optimistic_unchoked_peer = None
        self.gamma = 0.1
        self.r = 3
        self.alpha = 0.2
        self.possible_download_rates = dict()
        self.min_upload_needed = dict()
        self.rounds_unchoked_by = defaultdict(int)

        # Default value for u_ij (minimum upload capacity to give someone for them to unchoke us)
        self.default_min_upload_needed = self.up_bw / 4

        # Default value for d_ij (i's expected download rate if unchoked by j)
        self.default_possible_download_rates = self.up_bw / 4


    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects

        This will be called after update_pieces() with the most recent state.
        """
        if history.current_round() == 0:
            for peer in peers:
                self.min_upload_needed[peer.id] = self.default_min_upload_needed
                self.possible_download_rates[peer.id] = self.default_possible_download_rates

        need_list = []
        for i in range(len(self.pieces)):
            if self.pieces[i] < self.conf.blocks_per_piece:
                need_list.append(i)
        need_set = set(need_list)

        logging.debug("%s here: still need pieces %s" % (self.id, need_list))
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
        logging.debug("%s again.  It's round %d." % (self.id, round))

        # Don't upload if you don't receive requests
        if not requests:
            return []

        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course) has a list of Download objects for each Download to this peer in the previous round.

        requesters_ids = set(map(lambda request: request.requester_id, requests))

        # If first round, give unchoke spot to random agent. If later round, give to agent who gave us highest bandwidth
        if round == 0:
            # Randomly pick 4 users requesting pieces from us, and give each of them equal bandwidth
            if len(requesters_ids) < 4:
                peers_to_unchoke = list(requesters_ids)
            else:
                peers_to_unchoke = random.sample(requesters_ids, 4)

            bws = even_split(self.up_bw, len(peers_to_unchoke))
        else:
            # Keep track of who unchoked us in the past rounds and how many consecutive rounds they unchoked us
            unchoked_us_last_round = dict()
            downloaded_from_peer = defaultdict(int)
            for download in history.downloads[-1]:
                if download.from_id not in unchoked_us_last_round:
                    self.rounds_unchoked_by[download.from_id] += 1
                    unchoked_us_last_round[download.from_id] = 1
                downloaded_from_peer[download.from_id] += download.blocks
            for peer in peers:
                if peer.id not in unchoked_us_last_round:
                    self.rounds_unchoked_by[peer.id] = 0

            # Update parameters from the end of last round
            for peer in peers:
                if peer.id not in unchoked_us_last_round:
                    self.min_upload_needed[peer.id] *= 1 + self.alpha
                else:
                    self.possible_download_rates[peer.id] = downloaded_from_peer[peer.id]
                if self.rounds_unchoked_by[peer.id] >= 3:
                    self.min_upload_needed[peer.id] *= 1 - self.gamma

            # Determine who to unchoke by ordering by decreasing ratio d_ij/u_ij and choosing the k largest peers
            peers_sorted = sorted(requesters_ids, key=lambda p: self.possible_download_rates[p] / self.min_upload_needed[p],
                                  reverse=True)
            peers_to_unchoke = []
            bws = []
            sum_up_bw = 0
            for p in peers_sorted:
                sum_up_bw += self.min_upload_needed[p]
                if sum_up_bw > self.up_bw:
                    break
                peers_to_unchoke.append(p)
                bws.append(self.min_upload_needed[p])

        uploads = [Upload(self.id, peer_id, bw) for (peer_id, bw) in zip(peers_to_unchoke, bws)]

        return uploads
