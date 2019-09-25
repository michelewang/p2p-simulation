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
from random import sample 


class SKT_T1Std(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.dummy_state = dict()
        self.piece_availabilities = dict()
        self.dummy_state["cake"] = "lie"
    
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
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)
            n = min(self.max_requests, len(isect))
            # sort this based on the pieces in your piece availability dictionary
            sorted_by_rarest = sorted(isect, key=lambda piece: self.piece_availabilities[piece])

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

        returns: list of Upload objects which specify how much of its upload bandwidth to allocate
to any given peer. 
        In each round, this will be called after requests().
        
        """

        round = history.current_round()
        logging.debug("%s again.  It's round %d." % (
            self.id, round))
        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course) has a list of Download objects for each Download to this peer in the previous round.

        if round == 1:
            # randomly pick 4 users requesting pieces from us, and give each of them equal bandwidth
            requesters_ids = map(lambda request: request.requester_id, requests)
            chosen_peer_ids = random.sample(requesters_ids, 4)
            bws = even_split(self.up_bw, len(chosen_peer_ids))
        else:
            # pick the top 3 people who gave us the highest upload bandwidth in the past period
            # prev_upload = history.downloads[:-1]
            # BEN
            # last_round_uploads = [v[:-1] for v in history.uploads] # this is a list of uploads
            # last_round_uploads_flattened = [upload for sublist in last_round_uploads for upload in sublist] # just user uploads
            # my_uploaders = filter(lambda upload: upload.to_id == self.id, last_round_uploads_flattened)
            # find the top 3 peers who gave us the most download bandwidth (i.e. blocks)
            # top_peer_uploads = sorted(my_uploaders, key=lambda upload: upload.bw)[-3:]

            #MICHELE
            prev_uploads = history.uploads[-1]
            my_uploaders = filter(lambda upload: upload.to_id == self.id, prev_uploads)
            top_peer_uploads = sorted(my_uploaders, key=lambda upload:upload.bw)[-3:]
            top_peer_ids = map(lambda uploader: uploader.from_id, top_peer_uploads)
            bws = even_split(self.up_bw*(3/4), len(top_peer_ids))

            #optimistic unchoking




        # ACTUALLY: sort peers by people who have given you the highest upload bandwidth in the past period
        print "*************"
        print history.uploads


        # unchoke 
        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
            chosen = []
            bws = []
        else:
            logging.debug("Still here: uploading to a random peer")
            # change my internal state for no reason
            self.dummy_state["cake"] = "pie"

            request = random.choice(requests)
            chosen = [request.requester_id]
            # Evenly "split" my upload bandwidth among the one chosen requester
            bws = even_split(self.up_bw, len(chosen))

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]
            
        return uploads
