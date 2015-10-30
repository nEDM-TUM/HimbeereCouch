import cloudant
from .util import getmacid, getpassword

_server = None
_database_name = "nedm%2Fraspberries"

def set_server(srvr):
    """
    Set the current server that should be used

    :param srvr: server name
    :type srvr: str
    """
    global _server
    _server = srvr

def get_acct():
    """
    get the account object

    :rtype: cloudant.Account
    """
    if _server is None:
        raise Exception("Server not valid, not yet set!")
    acct = cloudant.Account(_server)
    if acct.login(str(getmacid()), str(getpassword())).status_code != 200:
        raise Exception("Server ({}) credentials invalid!".format(_server))
    return acct

def get_database():
    """
    get the database object
    
    :rtype: cloudant.Database
    """
    return get_acct()[_database_name]

def send_heartbeat(db=None, **kwargs):
    """
      Update the heartbeat document.  kwargs are passed into the document and
      must be json serializable

    :param db: database
    :type db: str 
    :param kwargs: keywords (must be JSON-serializable) passed in to heartbeat
    document

    """
    if db is None:
        db = get_database()
    hdoc = { "type" : "heartbeat" }
    hdoc.update(kwargs)
    db.design("nedm_default").put(
      "_update/insert_with_timestamp/{}_heartbeat".format(str(getmacid())),
      params=hdoc)


def get_processes_code():
    """
    get the process code from the database (returned by :func:`get_database`)
    This expects documents in the database that look like::

        {
          "type" : "macid_of_rasperry<int>", # i.e. value returned by :func:`himbeere.util.getmacid`
          "name" : "name of the code",
          "modules" : { # these are modules used by this local code
            "name_of_module1" : "<python code>",
            "name_of_module2" : "<python code>",
            ...
          },
          "global_modules" : { # these modules will be exported to *all*
                               # code in this database
            "name_of_global1" : "<python code>",
            "name_of_global2" : "<python code>"
          },
          "code" : "<python code>" # This is the main module, it *must* include a
                                   # `main` function
        }

    *Note*, all of these are optional.  If e.g. ``"code"`` is omitted, then only
    ``"global_modules"`` will essentially have any effect as they will be exported
    to other code in the database.

    :returns: dict - dictionary of code available in the database
    """
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
       code = d.get('modules', {})
       global_modules.update(d.get('global_modules', {}))
       if 'code' in d:
           code['main'] = d['code']
       if "main" in code:
           # Only add main code to return document
           anid = d.get("name", r["id"])
           ret_dic[anid] = { "id" : r["id"], "code" : code }

    for v in ret_dic.values():
       v.update(global_modules)

    return ret_dic
