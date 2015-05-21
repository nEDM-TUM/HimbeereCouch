import cloudant
from .util import getmacid, getpassword

_server = None
_database_name = "nedm%2Fraspberries"

def set_server(srvr):
    global _server
    _server = srvr

def get_acct():
    if _server is None:
        raise Exception("Server not valid!")
    acct = cloudant.Account(_server)
    if acct.login(str(getmacid()), str(getpassword())).status_code != 200:
        raise Exception("Server ({}) credentials invalid!".format(_server))
    return acct

def get_database():
    return get_acct()[_database_name]

def send_heartbeat(db=None, **kwargs):
    """
      Update the update document
    """
    if db is None:
        db = get_database()
    hdoc = { "type" : "heartbeat" }
    hdoc.update(kwargs)
    db.design("nedm_default").put(
      "_update/insert_with_timestamp/{}_heartbeat".format(str(getmacid())),
      params=hdoc)


def get_processes_code():
    db = get_database()
    aview = db.design("document_type").view("document_type")
    res = aview.get(params=dict(startkey=[getmacid()],
                                endkey=[getmacid(), {}],
                                include_docs=True,
                                reduce=False)).json()

    ret_dic = {}
    global_modules = {}
    for r in res['rows']:
       d = r['doc']
       code = {}
       if 'modules' in d:
           code.update(d['modules'])
       if 'global_modules' in d:
           global_modules.update(d['global_modules'])
       if 'code' in d:
           code['main'] = d['code']
       if "main" in code:
           # Only add main code to return document
           ret_dic[r["id"]] = code

    for v in ret_dic.values():
       v.update(global_modules)

    return ret_dic
