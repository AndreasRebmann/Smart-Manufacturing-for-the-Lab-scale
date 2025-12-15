import uuid
from threading import Thread
import copy
from datetime import datetime, timezone
import time
import sys
from opcua import ua, uamethod, Server, Client
from opcua.ua import NodeClass, NodeId, NodeIdType
from opcua.server.history_sql import HistorySQLite
import sqlite3
import csv
import pandas as pd
import os, argparse, json, requests
from graphQLSMIP import graphql
from opcutils import nodeSearch, updateServerNodes, updateClientNodes


sys.path.insert(0, "..")

#embed is useful for testing and troubleshooting
try:
    from IPython import embed
except ImportError:
    import code

    def embed():
        myvars = globals()
        myvars.update(locals())
        shell = code.InteractiveConsole(myvars)
        shell.interact()


if __name__ == "__main__":
    server = Server()
    server.set_endpoint("opc.tcp://local.machine.ip.address:4840/central_clientserver_name")
    server.set_server_name("central_clientserver_name")

    uri = "urn:project_name:opcua:central_clientserver_name"
    idx = server.register_namespace(uri)

    server.set_security_policy([
                ua.SecurityPolicyType.NoSecurity,
                ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt,
                ua.SecurityPolicyType.Basic256Sha256_Sign])

    #Folder for data nodes
    dataFolder = server.nodes.objects.add_folder(idx, "dataFolder")

    Device_1 = dataFolder.add_object(idx, "Device_1")
    Device_1.add_variable(idx, "Var_1",0).set_writable()
    Device_1.add_property(idx, "Prop_1", 1).set_writable() #properties generally do not change or are read often

    #following https://github.com/FreeOpcUa/python-opcua/blob/master/examples/server-datavalue-history.py
    # Configure server to use sqlite as history database (default is a simple memory dict)
    startTime = datetime.now(timezone.utc)
    dbname = "project_name_history"
    server.iserver.history_manager.set_storage(HistorySQLite(r"filepathforsqldb\{}.sql".format(dbname)))

    #SMIP setup
    smip = {
    "verbose": 0,
    "authenticator": "auth",
    "password": "pass",
    "name": "name",
    "role": "role",
    "url": "url",
    "bearer_token": ""
    }
    graphql = graphql(smip["authenticator"], smip["password"], smip["name"], smip["role"], smip["url"], smip["bearer_token"])
	
    smip_ids = {'Device_1_Var_1':123,'Device_1_Prop_1':124}

    server.start()

    smip_tag = {}
    tags = []
    tagnames = []
    for unit in dataFolder.get_children(): 
        for eachNode in unit.get_children(): 
            tags.append(eachNode)
            tagnames.append(unit.get_display_name().Text+"_"+eachNode.get_display_name().Text)
            smip_tag[eachNode.nodeid.to_string()] = smip_ids[unit.get_display_name().Text+"_"+eachNode.get_display_name().Text]

    server.historize_node_data_change(tags, period=None, count=10e6)

    try:
        i = 0                
        client = Client("client1_server_endpoint")
        targets = ["NodeName1"]
        Client1_read_targList = nodeSearch(client,targets)
        client = Client("client2_server_endpoint")
        targets = ["NodeName2"]
        searchPath = ["Objects", "2:dataFolder"]
        Client2_write_targList = nodeSearch(client,targets,searchPath)

        while True:
            #read from client1
            try:
                client = Client("client1_server_endpoint")
                nodeMap = [["NodeName1","Parent1"]]
                nodeVars = [Device_1.get_children()[0]]
                updateServerNodes(client,nodeMap,nodeVars,targList = Client1_read_targList)
            except Exception as e:
                print(f"Error encountered in reading Client1:{e}")
            
            #write to client2
            try:
                client = Client("client2_server_endpoint")
                nodeMap = [["NodeName2"]]
                nodeVars = [Device_1.get_children()[0].get_value()]
                updateClientNodes(client,nodeMap,nodeVars,targList = Client2_write_targList )
            except Exception as e:
                print(f"Error encountered writing to Client2:{e}")

            #build query for SMIP
            dataMutation = """mutation SendData {
                        """
            tagid = 0

            timestamp = datetime.strftime(datetime.now(timezone.utc),r"%Y-%m-%dT%H:%M:%SZ")
            for tag in tags:
                tagid = tagid + 1
                dataMutation+=(f"""ts{smip_tag[tag]}: replaceTimeSeriesRange(
                        input: {{
                        entries: [
                            {{ status: "0", timestamp: "{timestamp}", value: "{tag.get_value()}" }}
                        ]
                        attributeOrTagId: "{smip_tag[tag.nodeid.to_string()]}"
                        }}
                    ) {{
                        json
                    }}

                """)
            dataMutation+=("""}""")
            #send data to SMIP
            try:
                smp_response = graphql.post(dataMutation, bool(smip["verbose"]))
            except requests.exceptions.HTTPError as e:
                print("An error occured accessing the SM Platform!")
                print(e)
 
            print()
            print ("Got a Query response from SMIP")
            print(smp_response)

            i += 1
            time.sleep(1)
    finally:
        server.stop()
        #write database to csv
        endTime = datetime.now(timezone.utc)
        try:
            db = sqlite3.connect(r"filepathforsqldb\{}.sql".format(dbname))
            cur = db.cursor()
            #for all tags query all rows, append list of values timestamps, names, nodeid
            i = 0
            table = list([])
            for tag in tags:
                rows = cur.execute(f"SELECT SourceTimestamp, value FROM '{str(tag).split(";")[0][3:]+"_"+str(tag).split(";")[1][2:]}' WHERE SourceTimestamp BETWEEN '{startTime.strftime(r"%Y-%m-%d %H:%M:%S.%f")}' AND '{endTime.strftime(r"%Y-%m-%d %H:%M:%S.%f")}'").fetchall()
                for row in rows:
                    listrow = list(row)
                    listrow[0] = datetime.fromisoformat(listrow[0].replace(" ","T"))
                    listrow[0] = listrow[0].replace(microsecond=0)
                    listrow.append(tagnames[i])
                    table.append(listrow)
                i += 1
            #for all seconds (round down to seconds) if a value is in there, print it for that column
            if not rows:
                print("Error retrieving data from SQL database.")
            else:
                try:
                    startTime = startTime.replace(microsecond=0).replace(second=startTime.second-1)
                    endTime = endTime.replace(microsecond=0).replace(second=endTime.second+1)
                    df = pd.DataFrame(table, columns = ['Time','Value','Tag'])
                    df['Time'] = pd.to_datetime(df['Time'],utc=True)
                    df = df.drop_duplicates(['Time','Tag'],keep='last').pivot(index='Time',columns='Tag',values='Value')

                    freqindex = pd.date_range(start=startTime,end=endTime,freq='1s')

                    #forward fills empty cells
                    df = df.reindex(freqindex).ffill()
                    df.to_csv(r"filepathforsqldb\{}.csv".format((startTime.isoformat()[0:16]+dbname).replace(":","_")))
                except Exception as e:
                    print(f"Error in writing csv:{e}")
        except sqlite3.Error as e:
            print(f"Database error: {e}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            cur.close()
            db.close()
