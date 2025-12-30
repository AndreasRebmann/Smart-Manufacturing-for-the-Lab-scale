#Sambit Ghosh main author. Help taken from Eric Schmucker@BlazeMetrics for reading distribution data from sql file 


##BlazeImage_Full
#image_table (ts)

##DerivedData
#distribution_data (ts)
#trend_data (ts)
#channel_boundaries (static --> explore more)

##OriginalStatistics similar structure to DerivedData


import sqlite3
import shutil
import glob
import os
import datetime, pytz
import array

from opcua import ua, uamethod, Server
from time import sleep
i = 0
myRowStart=1

###################### GET LATEST FOLDER NAME AFTER BLAZE EXPERIMENT STARTS ######################

list_of_files = glob.glob('C:/BlazeMetrics_Experiments/*')
latest_file=max(list_of_files, key=os.path.getctime)
myPath=latest_file.replace("\\" , "/")

print('Reading data from location:')
print(myPath)
print()

######################################## GET BLAZE TREND SETTINGS INFORMATION #####################

if __name__ == "__main__":

    """
    Read SQLite3 db and get initial details
    """ 

    #Create a Tag dictionary
    myTagsName={}
    myTagsID={}
    opcVar={}

    #Define tables we want to read
    dataTimeSeries='trend_data'
    dataSettings='trend_settings'

    """
    Copy and Read main file
    """

    #Create connection with relevant database
    shutil.copyfile(myPath+'/DerivedData.db', myPath+'/myTest.db')
    conn=sqlite3.connect(myPath+"/myTest.db")
    cur=conn.cursor()

    #Use trend_settings information to setup tagnames, IDs to query from live database
    myQuery='SELECT * from '+ dataSettings #+ ' WHERE trend_index= ?'

    tagCount=0; 

    #For 12 trends
    for row in cur.execute(myQuery):
        tempStore=str(row[1]) + '|' + str(row[7]) + '|' + str(row[8]) + '|' + str(row[9]) + '|' + str(row[10]) + '|' + str(row[11]) 
        myTagsName[tagCount+1]=tempStore
        myTagsID[tagCount+1]=str(row[0])
        tagCount=tagCount+1


    #Close connection and remove temporary db file
    conn.close()
    os.remove(myPath+"/myTest.db")

    ############################################### CREATE LOCAL OPC-UA SERVER ####################

    """
    OPC-UA-Server Setup
    """
    server = Server()    
    print(server)

    endpoint = "opc.tcp://local.machine.ip.address:4840"
    server.set_endpoint(endpoint)

    servername = "BlazeMetrics-OPC-UA-Server"
    server.set_server_name(servername)

    """
    OPC-UA-Modeling
    """
    root_node = server.get_root_node()
    object_node = server.get_objects_node()
    idx = server.register_namespace("OPCUA_SERVER")
    myobj = object_node.add_object(idx, "DA_UA")
    print("Root Node ID                           : " , root_node)
    print("Object Node ID                         : " , object_node)
    print("Name Space and ID of Variable Object   : " , myobj)


    """
    OPC-UA-Server Add Variable
    """

    #Create Tag NameSpace(NS) and ID using Blaze trend_settings info 
    for tagNum in range(1,len(myTagsID)+1):
        opcVar[tagNum] = myobj.add_variable(idx ,myTagsName[tagNum],0,ua.VariantType.Float)
        print("NS-ID->"+myTagsName[tagNum]+" : ", opcVar[tagNum])


    #Add tag for Distribution vector (as a list)
    myTagsName[tagNum+1]='Distribution|Counts|LengthWeight'
    opcVar[tagNum+1] = myobj.add_variable(idx ,myTagsName[tagNum+1],0,ua.VariantType.Float)
    print("NS-ID->"+myTagsName[tagNum+1]+" : ", opcVar[tagNum+1])

################################################# START OPC-UA SERVER #############################
    
    server.start()
    timezone=pytz.timezone('US/Eastern')

################################################# GET DATA REAL TIME ##############################

    dataSettings='distribution_data'
    distro_index = 0
    weight_type = "length"

    try:
        while 1:
            #Create connection with relevant database
            shutil.copyfile(myPath+'/DerivedData.db', myPath+'/myTest.db')
            conn=sqlite3.connect(myPath+"/myTest.db")
            cur=conn.cursor()

            #Get data 
            try:
                myQuery='SELECT * from '+ dataTimeSeries + ' WHERE trend_index= ? AND rowid> ?'
            except:
                pass

            try:
                cur.execute(myQuery,(myTagsID[1],myRowStart))
            except:
                pass

            try:
                records=cur.fetchall()
            except:
                pass

            myRowEnd=len(records)

            #Read Tag Values
            for tagNum in range(1,14):        

                if tagNum<13:
                    myQuery='SELECT * from '+ dataTimeSeries + ' WHERE trend_index= ? AND rowid> ?'
                    try:
                        cur.execute(myQuery,(myTagsID[tagNum],myRowStart))
                        records=cur.fetchall()
                    except:
                        pass                
                
                    for dataRows in range(1,len(records)):
                        blazeDateTime1 = datetime.datetime.fromtimestamp(records[dataRows][1] / 1000.0, tz=datetime.timezone.utc)
                        try:
                            datavalue = ua.DataValue(float(records[dataRows][2]), serverTimestamp=blazeDateTime1)
                            opcVar[tagNum].set_value(datavalue)
                        except:
                            datavalue=float(0);

                elif tagNum==13:
                    params = (distro_index, weight_type, myRowStart)
                    try:
                        db_cursor = cur.execute("select timestamp_ms, weighted_values from distribution_data where distro_index=? and weight_type=? and rowid> ?", params)
                        data = [(timestamp_ms, array.array('d', weighted_values).tolist()) for timestamp_ms, weighted_values in db_cursor]

                        for ts, weighted_vals in data:
                            blazeDateTime2=datetime.datetime.fromtimestamp(ts / 1000.0, tz=datetime.timezone.utc)
                            datavalue2 = ua.DataValue(weighted_vals,serverTimestamp=blazeDateTime2)
                            opcVar[tagNum].set_value(datavalue2)

                    except:
                        datavalue2 = ua.DataValue(0,serverTimestamp=blazeDateTime1)
                        opcVar[tagNum].set_value(datavalue2)



            myRowStart=myRowEnd+1
            #Close connection and remove temporary db file
            conn.close()
            os.remove(myPath+"/myTest.db")

        #sleep(0.1)

    except KeyboardInterrupt:
        server.stop
   
