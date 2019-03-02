# Caitlin Sanders
# CIS 400: Assignment 2
# Due March 1, 2019

import twitter
import json
from functools import partial
import sys
import time
from urllib.error import URLError
from http.client import BadStatusLine
from sys import maxsize as maxint
from operator import itemgetter
from heapq import nlargest
import networkx as nx
import pylab as plt

# Authorization encapsulated. Own code.
def oauth_login():
  CONSUMER_KEY = 'Ajo3EGpy6RaIZsq0KanIB7Xbo'
  CONSUMER_SECRET = '86u5vGtVdCRvXH4J6Gorz6MtACyq7Pzh94KAdJr4QaFmgNaGKc'
  OAUTH_TOKEN = '2172576189-WAV5JnW36Am8sMjOZQJKxKD7q4rPFbP4axHMVLp'
  OAUTH_TOKEN_SECRET = 'nP6Hk5hRkTXVcR7JqP0oFGv5ZEn36kFLfQJJYKmC0K6EB'

  auth = twitter.oauth.OAuth(OAUTH_TOKEN,OAUTH_TOKEN_SECRET, CONSUMER_KEY, CONSUMER_SECRET)

  twitter_api = twitter.Twitter(auth=auth)
  return twitter_api

# Code from the Mining the Social Web 3rd Edition Chapter 20 Twitter Cookbook
# Makes API request to twitter
def make_twitter_request(twitter_api_func, max_errors=10, *args, **kw):
    # A nested helper function that handles common HTTPErrors. Return an updated
    # value for wait_period if the problem is a 500 level error. Block until the
    # rate limit is reset if it's a rate limiting issue (429 error). Returns None
    # for 401 and 404 errors, which requires special handling by the caller.
    def handle_twitter_http_error(e, wait_period=2, sleep_when_rate_limited=True):

        if wait_period > 3600: # Seconds
            print('Too many retries. Quitting.', file=sys.stderr)
            raise e

        if e.e.code == 401:
            print('Encountered 401 Error (Not Authorized)', file=sys.stderr)
            return None
        elif e.e.code == 404:
            print('Encountered 404 Error (Not Found)', file=sys.stderr)
            return None
        elif e.e.code == 429:
            print('Encountered 429 Error (Rate Limit Exceeded)', file=sys.stderr)
            if sleep_when_rate_limited:
                print("Retrying in 15 minutes...ZzZ...", file=sys.stderr)
                sys.stderr.flush()
                time.sleep(60*15 + 5)
                print('...ZzZ...Awake now and trying again.', file=sys.stderr)
                return 2
            else:
                raise e # Caller must handle the rate limiting issue
        elif e.e.code in (500, 502, 503, 504):
            print('Encountered {0} Error. Retrying in {1} seconds'\
                  .format(e.e.code, wait_period), file=sys.stderr)
            time.sleep(wait_period)
            wait_period *= 1.5
            return wait_period
        else:
            raise e

    # End of nested helper function
    wait_period = 2
    error_count = 0

    while True:
        try:
            return twitter_api_func(*args, **kw)
        except twitter.api.TwitterHTTPError as e:
            error_count = 0
            wait_period = handle_twitter_http_error(e, wait_period)
            if wait_period is None:
                return
        except URLError as e:
            error_count += 1
            time.sleep(wait_period)
            wait_period *= 1.5
            print("URLError encountered. Continuing.", file=sys.stderr)
            if error_count > max_errors:
                print("Too many consecutive errors...bailing out.", file=sys.stderr)
                raise
        except BadStatusLine as e:
            error_count += 1
            time.sleep(wait_period)
            wait_period *= 1.5
            print("BadStatusLine encountered. Continuing.", file=sys.stderr)
            if error_count > max_errors:
                print("Too many consecutive errors...bailing out.", file=sys.stderr)
                raise

# Code from the Mining the Social Web 3rd Edition Chapter 20 Twitter Cookbook
# Gets user profile dictionary
def get_user_profile(twitter_api, screen_names=None, user_ids=None):
    # Must have either screen_name or user_id (logical xor)
    assert (screen_names != None) != (user_ids != None), \
    "Must have screen_names or user_ids, but not both"

    items_to_info = {}

    items = screen_names or user_ids

    while len(items) > 0:
        items_str = ','.join([str(item) for item in items[:100]])
        items = items[100:]

        if screen_names:
            response = make_twitter_request(twitter_api.users.lookup,
                                            screen_name=items_str)
        else: # user_ids
            response = make_twitter_request(twitter_api.users.lookup,
                                            user_id=items_str)

        for user_info in response:
            if screen_names:
                items_to_info[user_info['screen_name']] = user_info
            else: # user_ids
                items_to_info[user_info['id']] = user_info

    return items_to_info

# Code from the Mining the Social Web 3rd Edition Chapter 20 Twitter Cookbook
# Gets ids of friends and followers in lists
def get_friends_followers_ids(twitter_api, screen_name=None, user_id=None,
                              friends_limit=maxint, followers_limit=maxint):

    # Must have either screen_name or user_id (logical xor)
    assert (screen_name != None) != (user_id != None), \
    "Must have screen_name or user_id, but not both"

    get_friends_ids = partial(make_twitter_request, twitter_api.friends.ids,
                              count=5000)
    get_followers_ids = partial(make_twitter_request, twitter_api.followers.ids,
                                count=5000)

    friends_ids, followers_ids = [], []

    for twitter_api_func, limit, ids, label in [
                    [get_friends_ids, friends_limit, friends_ids, "friends"],
                    [get_followers_ids, followers_limit, followers_ids, "followers"]
                ]:

        if limit == 0: continue

        cursor = -1
        while cursor != 0:

            # Use make_twitter_request via the partially bound callable...
            if screen_name:
                response = twitter_api_func(screen_name=screen_name, cursor=cursor)
            else: # user_id
                response = twitter_api_func(user_id=user_id, cursor=cursor)

            if response is not None:
                ids += response['ids']
                cursor = response['next_cursor']

            print('Fetched {0} total {1} ids for {2}'.format(len(ids),\
                  label, (user_id or screen_name)),file=sys.stderr)

            if len(ids) >= limit or response is None:
                break

    return friends_ids[:friends_limit], followers_ids[:followers_limit]

# Own function. Returns the follower count of the user id inputted
def get_followers(ids):
    return get_user_profile(twitter_api, user_ids=ids)

# Own function. Returns a list of the id's of the 5 most popular (most friends) of the user id input's reciprocal friends
def get_most_popular(twitter_api, id):
    # Friends and followers of user with 'id'
    friends_ids, followers_ids = get_friends_followers_ids(twitter_api,
                                                           user_id=id,
                                                           friends_limit=5000,
                                                           followers_limit=5000)
    # Reciprocal friends of user with 'id' (distance = 1)
    reciprocal_friends = list(set(friends_ids).intersection(followers_ids))

    # Dictionary of id:dict of user info of reciprocal friends
    reciprocal__followers = get_followers(reciprocal_friends)
    # Dictionary of id:followers of reciprocal friends
    reciprocal_final =  {x:info.get('followers_count') for (x,info) in reciprocal__followers.items()}
    # List of id's of 5 most popular reciprocal friends
    return nlargest(5, reciprocal_final, key=reciprocal_final.get)

# Mix of own code and code from the Mining the Social Web 3rd Edition Chapter 20 Twitter Cookbook
# Returns list of the 100 most popular users starting at the user "screen name"

def crawl_followers(twitter_api, screen_name, total_users=100):

    # Finding id of screen_name entered
    seed_id = str(twitter_api.users.show(screen_name=screen_name)['id'])
    return_list = [int(seed_id)]
    # Creating graph using NetworkX
    g = nx.Graph()
    g.add_node(int(seed_id))

    # Getting first 5 most popular friends of first user
    next_queue = get_most_popular(twitter_api, seed_id)
    g.add_edges_from([(int(seed_id),x) for x in next_queue])

    # Using Breadth first seach to find the 5 most popular friends of the first user's most popular friends and so on until 100 users
    users = g.number_of_nodes()
    while users < total_users:
        (queue, next_queue) = (next_queue, [])
        for fid in queue:
            g.add_node(fid)
            five_more = get_most_popular(twitter_api, fid)
            g.add_edges_from([(fid,x) for x in five_more])
            next_queue += five_more
            users = g.number_of_nodes()
            if users > total_users:
                return_list.extend(next_queue)
                return [return_list,g]
        return_list.extend(next_queue)
    # Print calls for testing
    #    print("Currently we have ", return_list)
    return [return_list,g]

# Runner program
twitter_api = oauth_login()
screen_name="caitsands"
final = crawl_followers(twitter_api, screen_name)
# Print calls for testing
#print("Test: ", final[0])
g = final[1]
# Using NetworkX to draw graph 'g'
nx.draw(g)
# Using Matplotlib to save graph
plt.savefig('graph.png')
# Calculating number of nodes, edges, diameter and average distance of graph 'g' using NetworkX
print("Number of nodes = ", g.number_of_nodes())
print("Number of edges = ", g.number_of_edges())
print("Diameter = ", nx.diameter(g))
print("Average distance = ", nx.average_shortest_path_length(g))


# Print calls for testing
# List of friends and followers of user "caitsands"
#friends_ids, followers_ids = get_friends_followers_ids(twitter_api,
#                                                           screen_name="caitsands",
#                                                           friends_limit=5000,
#                                                           followers_limit=5000)

# Reciprocal friends of user "caitsands" (distance = 1)
#reciprocal_friends = list(set(friends_ids).intersection(followers_ids))

#print("Friends: ", friends_ids, "\n")
#print("# of Friends: ",len(friends_ids), "\n")
#print("Followers: ", followers_ids, "\n")
#print("# of Followers: ",len(followers_ids), "\n")
#print("Reciprocal friends: ", reciprocal_friends, "\n")
#print("# of Reciprocal friends: ", len(reciprocal_friends), "\n")
#print("5 most popular reciprocal friends: ", get_most_popular(twitter_api,"2172576189"), "\n")
