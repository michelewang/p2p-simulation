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


class SKT_T1Tourney(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.piece_availabilities = dict()
        self.optimistic_unchoked_peer = None
        self.optimistic_proportion = 0.1
        self.need_set = set()
        self.peer_by_rarest_pieces = {}

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
        self.need_set = set(need_list)

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
        peer_by_rarest_pieces_temp = dict()
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(self.need_set)
            n = min(self.max_requests, len(isect))
            sorted_by_rarest = sorted(isect, key=lambda piece: self.piece_availabilities[piece])
            if sorted_by_rarest is None:
                logging.debug("No request; no peers have our needed pieces")
                return []
            
            # rarity metric is how rare player's 2 rarest pieces are that we need. smaller is better
            print(sorted_by_rarest)
            top_two_rarest = sum(sorted_by_rarest[:2])
            print(top_two_rarest)
            peer_by_rarest_pieces_temp[peer.id] = top_two_rarest

            # This would be the place to try fancier piece-requesting strategies
            # to avoid getting the same thing from multiple peers at a time.

            # Take the top n pieces from the dictionary and get the next-needed blocks in order
            for piece_id in sorted_by_rarest[:n]:
                start_block = self.pieces[piece_id]
                r = Request(self.id, peer.id, piece_id, start_block)
                requests.append(r)

        logging.debug("Requests from {}: {}".format(self.id, requests))
        self.peer_by_rarest_pieces = peer_by_rarest_pieces_temp
        self.peer_by_rarest_pieces = sorted(self.peer_by_rarest_pieces, key=lambda peer: self.peer_by_rarest_pieces[peer])
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

        requesters_ids = set(map(lambda request: request.requester_id, requests))

        # find top two rarest pieces each player has
        
        # If first round, give unchoke spot to random agent. If later round, give to agent who gave us highest bandwidth
        if round == 0:
            # Randomly pick 4 users requesting pieces from us, and give each of them equal bandwidth
            if len(requesters_ids) < 4:
                peers_to_unchoke = list(requesters_ids)
            else:
                peers_to_unchoke = random.sample(requesters_ids, 4)
        else:
            downloads = history.downloads[-1]
            down_bw = defaultdict(int)
            for download in downloads:
                if download.from_id in requesters_ids:
                    down_bw[download.from_id] += download.blocks
            if round == 1:
                top_downloads = sorted(requesters_ids, key=lambda x: down_bw[x])
            else:
                downloads2 = history.downloads[-2]
                for download2 in downloads2:
                    if download2.from_id in requesters_ids:
                        down_bw[download2.from_id] += download2.blocks
                top_downloads = sorted(requesters_ids, key=lambda x: down_bw[x])
            peers_to_unchoke = top_downloads[-3:]
           
        # optimistically unchoke the peer with the most number of pieces we need
        needed_pieces_by_peer = dict()
        for p in peers:
            count_pieces = 0
            if p.id in requesters_ids:
                # count # of pieces they have
                for needed_piece in self.need_set:
                    if needed_piece in p.available_pieces:
                        count_pieces += 1
            needed_pieces_by_peer[p.id] = count_pieces
        peers_with_most_needed_pieces = sorted(needed_pieces_by_peer.items(), reverse=True, key=lambda item: item[1])
        
        # Optimistic unchoking every 3 rounds: choose an agent with most number of needed pieces who isn't already in peers_to_unchoke
        if round % 3 == 0 and len(requesters_ids) > len(peers_to_unchoke):
            peer_with_rarest = list(self.peer_by_rarest_pieces)[0]
            self.optimistic_unchoked_peer = peer_with_rarest
            peer_unchoked_index = 1
            while self.optimistic_unchoked_peer in peers_to_unchoke:
                self.optimistic_unchoked_peer = list(peer_with_rarest)[peer_unchoked_index]
                peer_unchoked_index += 1
            '''
            peer_with_most_pieces_id = list(peers_with_most_needed_pieces)[0]
            self.optimistic_unchoked_peer = peer_with_most_pieces_id
            peer_unchoked_index = 1
            while self.optimistic_unchoked_peer in peers_to_unchoke:
                self.optimistic_unchoked_peer = list(peers_with_most_needed_pieces)[peer_unchoked_index]
                peer_unchoked_index += 1
            '''

        # If we have spots left, add the peer from optimistic unchoking
        if len(peers_to_unchoke) < 4:
            peers_to_unchoke.append(self.optimistic_unchoked_peer)

        bws = even_split(self.up_bw, len(peers_to_unchoke))
        uploads = [Upload(self.id, peer_id, bw) for (peer_id, bw) in zip(peers_to_unchoke, bws)]

        return uploads
