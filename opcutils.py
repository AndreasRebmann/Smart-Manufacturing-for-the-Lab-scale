from opcua import ua, uamethod, Server, Client
from opcua.ua import NodeClass, NodeId, NodeIdType

#deepseek assistance was used in writing the nodeSearch function
def nodeSearch(client,targets,searchPath=None):
    nodeList = []
    try:
        client.connect()

        if searchPath is None:
            searchPath = ["0:Objects"]
        elif isinstance(searchPath, str):
            searchPath = [searchPath]
        
        currentNode = client.get_root_node()
        for paths in searchPath:
            currentNode = currentNode.get_child(paths)
        
        targetset = set(targets)

        def checkNode(node, parentName=None):
            try:
                nodeName = node.get_display_name().Text
                nodeClass = node.get_node_class()

                if nodeName in targetset:
                    nodeData = {
                        "Name" : nodeName,
                        "ID" : node.nodeid.to_string(),
                        "Parent" : parentName,
                        "Class" : nodeClass.name
                    }
                    if nodeClass == NodeClass.Variable:
                        try:
                            nodeData["Val"] = node.get_value()
                            nodeData["Type"] = str(node.get_data_type())
                        except Exception as e:
                            nodeData["Val"] = f"Error reading value: {str(e)}"
                    nodeList.append(nodeData)
                newParent = nodeName if nodeClass == NodeClass.Object else parentName

                for child in node.get_children():
                    checkNode(child, newParent)
            except Exception as e:
                print(f"Error processing node {node}: {e}")
        checkNode(currentNode)

        return nodeList
    finally:
        client.disconnect()

def updateServerNodes(client,nodeMap,nodeVars,targList=None,searchPath=None,targets=None):
    if targList is None:
        if targets is None:
            print("Error: No map or list of targets provided.")
        else:
            targList = nodeSearch(client,targets,searchPath)
    i = 0
    for key in nodeMap:
        if len(key) == 1:
            update = next((nodeInfo for nodeInfo in targList if nodeInfo["Name"]==key[0]), None)
        elif len(key) == 2:
            update = next((nodeInfo for nodeInfo in targList if (nodeInfo["Name"]==key[0] and nodeInfo["Parent"]==key[1])), None)
        else:
            print(f"Error: Only keys of Name or Name and Parent accepted, key:{key}")
        if update is None:
            print(f"Error: No nodes found matching key:{key} in server:{client.server_url}")
        else:
            nodeVars[i].set_value(update["Val"])
        update = None
        i += 1

def updateClientNodes(client,nodeMap,nodeVars,targList=None,searchPath=None,targets=None):
    if targList is None:
        if targets is None:
            print("Error: No map or list of targets provided.")
        else:
            targList = nodeSearch(client,targets,searchPath)
    client.connect()
    i = 0
    for key in nodeMap:
        if len(key) == 1:
            update = next((nodeInfo for nodeInfo in targList if nodeInfo["Name"]==key[0]), None)
        elif len(key) == 2:
            update = next((nodeInfo for nodeInfo in targList if (nodeInfo["Name"]==key[0] and nodeInfo["Parent"]==key[1])), None)
        else:
            print(f"Error: Only keys of Name or Name and Parent accepted, key:{key}")
        if update is None:
            print(f"Error: No nodes found matching key:{key} in server:{client.server_url}")
        else:
            client.set_values([client.get_node(update["ID"])], [nodeVars[i]])
        update = None
        i += 1
    client.disconnect()
