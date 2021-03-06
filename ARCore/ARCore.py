import pymel.core as pm
import maya.cmds as cmds
from maya import OpenMaya
import maya.api.OpenMaya as OpenMaya2
from maya import OpenMayaAnim
import ctrSaveLoadToJson
import inspect
import os

import logging
logging.basicConfig()
logger = logging.getLogger('ARCore:')
logger.setLevel(logging.DEBUG)


def cloneWithHierarchy(root, type="transform", suffix="_dup"):
    """
    Clone the given joint root, clone the hierarchy with transform nodes
    :param root(str or pm):
    :param type(str): type of output objects
    :return:
    """
    # check type
    root = pm.PyNode(root) if isinstance(root, str) else root
    allChildren = [i for i in root.listRelatives(ad=True) if isinstance(i, pm.nodetypes.Transform) or isinstance(i, pm.nodetypes.Joint)]

    allChildren.append(root)  # copy root too

    suffix = "_"+suffix

    if type == "transform":
        dupFunc = lambda x: pm.group(empty=True, w=True, name=str(x) + suffix)
    elif type == "locator":
        dupFunc = lambda x: pm.spaceLocator(name=str(x) + suffix)
    elif type == "joint":
        dupFunc = lambda x: pm.createNode("joint", name=str(x) + suffix)

    allDuplicated = []
    for child in allChildren:
        dup = dupFunc(child)
        pm.xform(dup, ws=True, m=pm.xform(child, q=True, ws=True, m=True))
        allDuplicated.append(dup)

    for i, child in enumerate(allChildren):
        pChild = child.firstParent()
        logger.debug("Parent %s" %str(pChild))
        logger.debug("Obj:  %s" %str(child))
        if pChild in allChildren:
            logger.debug("%s in allChildren" % (pChild))
            pChildId = allChildren.index(pChild)
            logger.debug("Parent id: %s" % pChildId)
            allDuplicated[pChildId].addChild(allDuplicated[i])
            if type == "joint":
                pm.makeIdentity(allDuplicated[i],apply=True, r=True, t=False, s=False)
                jointP = allDuplicated[i].firstParent()
                if not jointP in allDuplicated:
                    pm.ungroup(jointP)

    return allDuplicated, allChildren


def nearestGeometries(keys, geometries, distance=0.5):
    """
    return all the geometries inside the distance range
    :param keys: reference geometries
    :param geometries: geametries to check
    :return: geometries inside the range distance
    """
    nearestGeos = set()  # save here the nearest geometries

    # check geometries
    for i in range(len(geometries)):
        geometries[i] = pm.PyNode(geometries[i]) if isinstance(geometries[i], str) else geometries[i]
        geometries[i] = geometries[i].getShape() if isinstance(geometries[i], pm.nodetypes.Transform) else geometries[i]

    # time range
    startTime = int(pm.playbackOptions(minTime=True, q=True))
    endTime = int(pm.playbackOptions(maxTime=True, q=True))


    for geo in geometries:
        # check each geometry
        geoSelList = OpenMaya.MSelectionList()
        geoSelList.add(str(geo))
        geoDag = OpenMaya.MDagPath()
        geoSelList.getDagPath(0, geoDag)
        MFnGeoM = OpenMaya.MFnMesh(geoDag)

        found = False
        # check all vertices for element
        # time frame
        for stime in range(startTime, endTime, 24):
            pm.currentTime(stime)

            for key in keys:
                key = pm.PyNode(key) if isinstance(key, str) else key
                key = key.getShape() if isinstance(key, pm.nodetypes.Transform) else key

                # create a iterator
                mselection = OpenMaya.MSelectionList()
                mselection.add(str(key))
                mdagPath = OpenMaya.MDagPath()
                mselection.getDagPath(0, mdagPath)
                meshIt = OpenMaya.MItMeshVertex(mdagPath)

                #iterate over the vertices
                while not meshIt.isDone():
                    vPos = meshIt.position(OpenMaya.MSpace.kWorld)
                    # check nearestPoint
                    mPoint = OpenMaya.MPoint()
                    MFnGeoM.getClosestPoint(vPos, mPoint, OpenMaya.MSpace.kWorld)  # maybe here get error
                    vecDistance = OpenMaya.MVector(vPos - mPoint)

                    if vecDistance.length() <= distance:
                        logger.debug("point Found at: %s" % vecDistance.length())
                        nearestGeos.add(geo)
                        found = True
                        break

                    meshIt.next()

                if found:
                    break

            if found:
                found = False
                break

    return nearestGeos


def getCurrentPath():
    """
    Get the ARCore.py path
    :return: ARCore.py path
    """
    #print __name__
    #print inspect.currentframe()
    #print inspect.getfile(inspect.currentframe())
    #print os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    #print os.path.abspath(inspect.getfile(inspect.currentframe()))
    return os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))


### to mel code ###
def toMelCode(code):
    """
    Convert a python code to be launched from mel
    :param code:
    :return:
    """
    code = code.replace("\"", "'")
    codesplit = code.split('\n')
    melCode = 'python("' + '\\n"+\n"'.join(codesplit) + '");'
    return melCode


def sortByPosition(key):
    """
    sort the list be translate x
    :return:
    """
    return key.getTranslation("world")[0]


def createRoots(listObjects, suffix='root'):
    """
    Create root on elements, respecting their present hierarchy.
    Args:
        listObjects(list)(pm.Transform)(pm.Joint): list of transforms to create root, on joints set joint orient to 0
        suffix(str): suffix for the root grp

    Returns:
        roots(list): list of roots
    """
    # check type
    if not isinstance(listObjects, list):
        listObjects = [listObjects]

    roots = []
    for arg in listObjects:
        try:
            parent = arg.firstParent()
        except:
            parent = None
        # explanation: pm getTransformation gives transform matrix in object space.
        # so we need to use pm.xform()
        rootGrp = pm.group(em=True, name='%s_%s' % (arg, suffix))
        matrixTransform = pm.xform(arg, q=True, ws=True, m=True)
        pm.xform(rootGrp, ws=True, m=matrixTransform)

        if parent:
            parent.addChild(rootGrp)
        rootGrp.addChild(arg)

        # if is a joint, assegure reset values
        if isinstance(arg, pm.nodetypes.Joint):
            for axis in ('X', 'Y', 'Z'):
                arg.attr('jointOrient%s' % axis).set(0.0)

            arg.setRotation((0,0,0), 'object')

        roots.append(rootGrp)

    return roots


def createController (name, controllerType, chName, path, scale=1.0, colorIndex=4):
    """
    Args:
        name: name of controller
        controllerType(str): from json controller types
        chName: name of json file
        path: path where is json file
    return:
        controller: pymel transformNode
        transformMatrix: stored position
    """
    controller, transformMatrix = ctrSaveLoadToJson.SaveLoadControls.ctrLoadJson(controllerType, chName, path, scale, colorIndex)
    controller = pm.PyNode(controller)
    controller.rename(name)

    shapes = controller.listRelatives(s=True)
    # hide shape attr
    for shape in shapes:
        for attr in ('aiRenderCurve', 'aiCurveWidth', 'aiSampleRate', 'aiCurveShaderR', 'aiCurveShaderG', 'aiCurveShaderB'):
            pm.setAttr('%s.%s' % (str(shape), attr), channelBox=False, keyable=False)

    pm.xform(controller, ws=True, m=transformMatrix)
    return controller


def jointPointToController(joints, controller):
    """
    TODO: input scale too. first read if scale is connected to something, if it is, combine
    create a controller, create a root for the controller and point constraint to joint
    Args:
        joints(list(Joint)): joint where create controller
        controller(Transform): controller object
    Returns:
        list: [controller], [root], [pointConstraint]
    """
    controllerList = []
    rootList = []
    pointConstraintList=[]
    aimGrpList = []
    for i, joint in enumerate(joints):
        if i == 0:
            controllerDup = controller
        else:
            controllerDup = controller.duplicate()[0]

        pm.xform(controllerDup, ws=True, m=pm.xform(joint, ws=True, q=True, m=True))
        controllerRoot = createRoots([controllerDup])[0]
        # point constraint
        parentConstraint = pm.parentConstraint(joint, controllerRoot)

        # append to lists
        controllerList.append(controllerDup)
        rootList.append(controllerRoot)
        pointConstraintList.append(parentConstraint)
        # lock attr
        lockAndHideAttr(controllerDup, False, False, True)
        for axis in ('Y', 'Z'):
            controllerDup.attr('rotate%s' % axis).lock()
            pm.setAttr('%s.rotate%s' % (str(controllerDup), axis), channelBox=False, keyable=False)

    return controllerList, rootList, pointConstraintList


def arrangeListByHierarchy(itemList):
    """
    Arrange a list by hierarchy
    p.e [[toea1, toea2, ...], [toeb, toeb_tip]]
    Args:
        itemList:
    Returns(list(list)): final list
    """
    def hierarchySize(obj):
        # key func for sort
        fullPath = obj.fullPath()
        sizeFullPath = fullPath.split('|')
        return len(sizeFullPath)

    itemListCopy = list(itemList)  # copy of the toes list
    itemListArr = []
    while len(itemListCopy):
        toeJoint = []
        firstJoint = itemListCopy.pop(0)
        toeJoint.append(firstJoint)
        for joint in firstJoint.listRelatives(ad=True):
            if joint in itemListCopy:
                toeJoint.append(joint)
                itemListCopy.remove(joint)

        # sort the list to assure a good order
        itemListArr.append(sorted(toeJoint, key=hierarchySize))
    logger.debug('arrangeListByHierarchy: sorted: %s' % itemListArr)

    return itemListArr


def findMirrorPoints(listObjects, mirrorVector=(-1,1,1), precision=0.01):
    """
    Given a list of transform nodes, organize a list with each respectivaly mirror point
    p.e [[objLeft, objRight], [obj2Left, obj2Right], ...]
    :param listObjects:
    :param mirrorVector: x y z value positive or negative
    :param precision:
    :return:
    """
    # check type
    mirrorVector = checkVectorType(mirrorVector)

    # save here the results
    mirrorObjectsList = []
    noMirrorObjectsList = []
    # iterate half list
    while len(listObjects):
        candidate = None
        paired = []
        # get obj positions
        obj = listObjects.pop()
        objPos = pm.datatypes.Vector(obj.getTranslation('world'))
        # get search vector
        searchVector = pm.datatypes.Vector(0,0,0)
        for axis in range(3):
            searchVector[axis] = objPos[axis] * mirrorVector[axis]

        for mirrorObj in listObjects:
            # compare positions
            diferenceVector = mirrorObj.getTranslation('world') - searchVector
            if diferenceVector.length() <= precision:
                if not candidate:
                    candidate = mirrorObj

                # check if new candidate is nearest
                elif candidate and diferenceVector.length() < pm.datatypes.Vector(candidate.getTranslation('world') -
                                                                                  searchVector).length():
                    candidate = mirrorObj

        if candidate:
            paired.append(obj)
            paired.append(candidate)
            # remove from list
            listObjects.remove(candidate)
            # and add to return list
            mirrorObjectsList.append(paired)

        # no candidate
        else:
            noMirrorObjectsList.append(obj)


    return mirrorObjectsList, noMirrorObjectsList


########################
##Attribute Operations##
########################
def lockAndHideAttr(obj, translate=False, rotate=False, scale=False):
    """
    lock and hide transform attributes
    # TODO: add limit operations
    Args:
        obj(pm.Trasform): Element to lock and hide
        translate(True): true, lock and hide translate
        rotate(True): true, lock and hide rotate
        scale(True): true, lock and hide scale
    """
    if isinstance(obj, list):
        itemList = obj
    else:
        itemList = []
        itemList.append(obj)

    for item in itemList:
        if translate:
            item.translate.lock()
            for axis in ('X', 'Y', 'Z'):
                pm.setAttr('%s.translate%s' % (str(item), axis), channelBox=False, keyable=False)
        if rotate:
            item.rotate.lock()
            for axis in ('X', 'Y', 'Z'):
                pm.setAttr('%s.rotate%s' % (str(item), axis), channelBox=False, keyable=False)
        if scale:
            item.scale.lock()
            for axis in ('X', 'Y', 'Z'):
                pm.setAttr('%s.scale%s' % (str(item), axis), channelBox=False, keyable=False)


def calcDistances(pointList,vector=False):
    """
    Calculate de distance between the points in the given list. 0->1, 1->2, 2->3...
    Args:
        pointList(List)(pm.Transform):
        vector(bool): true: use vectors to calculate distances. False: read x value of each element. if points are joints, better use False
    Returns:
        (list): with distances
        (float): total distance
    """
    distancesList = []
    totalDistance = 0
    if vector:
        for i, point in enumerate(pointList):
            if i == len(pointList)-1:
                continue
            point1 = point.getTranslation('world')
            point2 = pointList[i+1].getTranslation('world')

            vector = point2 - point1
            vector = OpenMaya.MVector(vector[0],vector[1],vector[2])
            # length of each vector
            length = vector.length()

            distancesList.append(vector.length())
            totalDistance += length

    else:  # simply read X values
        for point in pointList[1:]:
            xtranslateValue = point.translateX.get()
            totalDistance += xtranslateValue
            distancesList.append(xtranslateValue)

    return distancesList, totalDistance


def syncListsByKeyword(primaryList, secondaryList, keyword=None):
    """
    arrange the secondary list by each element on the primary, if they are equal less the keyword
    if not keyword, the script will try to find one, p.e:
    list1 = ['akona_upperArm_left_joint','akona_foreArm_left_joint','akona_arm_end_left_joint']
    list2 = ['akona_upperArm_twist1_left_joint','akona_upperArm_twist2_left_joint','akona_foreArm_twist1_left_joint', 'akona_foreArm_twist2_left_joint']
    keyword: twist
    Returnsn : [['akona_upperArm_twist1_left_joint', 'akona_upperArm_twist2_left_joint'], ['akona_foreArm_twist1_left_joint', 'akona_foreArm_twist2_left_joint'], []]

    """
    filterChars = '1234567890_'
    # if not keyword try to find one
    if not keyword:
        count = {}
        # count how many copies of each word we have, using a dictionary on the secondary list
        for secondaryItem in secondaryList:
            for word in str(secondaryItem).split('_'):
                for fChar in filterChars:
                    word = word.replace(fChar, '')
                # if word is yet in dictionary, plus one, if not, create key with word and set it to one
                # explanation: dict.get(word, 0) return the value of word, if not, return 0
                count[word] = count.get(word, 0) + 1
        # key word must not be in primary list
        wordsDetect = [word for word in count if count[word] == len(secondaryList) and word not in str(primaryList[0])]

        if len(wordsDetect) != 1:
            logger.info('no keyword detect')
            return
        keyword = wordsDetect[0]

    arrangedSecondary = []
    # arrange by keyword
    for primaryItem in primaryList:
        actualList = []
        for secondaryItem in secondaryList:
            splitStr = str(secondaryItem).partition(keyword)
            indexCut = None
            for i, char in enumerate(splitStr[-1]):
                if char in filterChars:
                    indexCut = i + 1
                else:
                    break

            compareWord = splitStr[0] + splitStr[-1][indexCut:]
            if compareWord == str(primaryItem):
                actualList.append(secondaryItem)

        arrangedSecondary.append(actualList)

    return arrangedSecondary


def relocatePole(pole, joints, distance=1):
    """
    TODO: use pm math classes, and reduce code
    relocate pole position for pole vector
    at the moment, valid for 3 joints.
    not calculate rotation
    Args:
        pole(pm.Transform): PyNode of pole
        joints(list)(pm.Transform): list of joints, pm nodes
        distance(float): distance from knee
    """
    # first vector
    position1 = joints[0].getTranslation('world')
    position2 = joints[1].getTranslation('world')
    vector1 = OpenMaya.MVector(position2[0]-position1[0],position2[1]-position1[1],position2[2]-position1[2])
    vector1.normalize()

   # second vector
    position1 = joints[-1].getTranslation('world')
    position2 = joints[-2].getTranslation('world')
    vector2 = OpenMaya.MVector(position2[0]-position1[0],position2[1]-position1[1],position2[2]-position1[2])
    vector2.normalize()

    # z vector
    poleVector = (vector1 + vector2)
    poleVector.normalize()

    # x vector cross product
    xVector = vector2 ^ poleVector
    xVector.normalize()

    # y vector cross product
    yVector = poleVector ^ xVector
    yVector.normalize()

    pole.setTransformation([xVector.x, xVector.y, xVector.z, 0, yVector.x, yVector.y, yVector.z, 0, poleVector.x, poleVector.y, poleVector.z, 0,
                       poleVector.x * distance + position2[0], poleVector.y * distance + position2[1], poleVector.z * distance + position2[2], 1])


def snapCurveToPoints(points, curve, iterations=4, precision=0.05):
    """
    Snap curve to points moving CV's of the nurbsCurve
    Args:
        points(list): transform where snap curve
        curve(pm.nurbsCurve): curve to snap
        iterations(int): number of passes, higher more precise. default 4
        precision(float): distance between point and curve the script is gonna take as valid. default 0.05
    """
    selection = OpenMaya.MSelectionList()
    selection.add(str(curve))
    dagpath = OpenMaya.MDagPath()
    selection.getDagPath(0, dagpath)

    mfnNurbsCurve = OpenMaya.MFnNurbsCurve(dagpath)

    for i in range(iterations):
        for joint in points:
            jointPos = joint.getTranslation('world')
            jointPosArray = OpenMaya.MFloatArray()
            util = OpenMaya.MScriptUtil()
            util.createFloatArrayFromList(jointPos, jointPosArray)

            mPoint = OpenMaya.MPoint(jointPosArray[0], jointPosArray[1], jointPosArray[2], 1)
            closestPointCurve = mfnNurbsCurve.closestPoint(mPoint, None, 1, OpenMaya.MSpace.kWorld)

            mvector = OpenMaya.MVector(mPoint - closestPointCurve)

            if mvector.length() < precision:
                continue

            # nearest cv
            cvArray = OpenMaya.MPointArray()
            mfnNurbsCurve.getCVs(cvArray, OpenMaya.MSpace.kWorld)
            nearest = []
            lastDistance = None

            for n in range(mfnNurbsCurve.numCVs()):
                if n == 0 or n == cvArray.length() - 1:
                    continue

                distance = mPoint.distanceTo(cvArray[n])

                if not nearest or distance < lastDistance:
                    nearest = []
                    nearest.append(cvArray[n])
                    nearest.append(n)

                    lastDistance = distance

            mfnNurbsCurve.setCV(nearest[1], nearest[0] + mvector, OpenMaya.MSpace.kWorld)

    mfnNurbsCurve.updateCurve()

class APIHelp:
    """
    Help Operations using the API, and help funcs to use the API
    """
    @staticmethod
    def findAttr(attr, *args):
        """
        Find objects with the desired attr. API2
        Args:
            attr: Attribute desired
            *args: objects we want to check, if no *args check entire scene

        Returns: Pymel objects List that contain the attribute
        """

        mselList = OpenMaya2.MSelectionList()
        # if some args are given
        if len(args):
            for i in args:
                mselList.add(i)
        # no args check entire scene
        else:
            mselList.add('*')

        # msellist iterator
        mselList_It = OpenMaya2.MItSelectionList(mselList, OpenMaya2.MFn.kTransform)

        transformReturn = []

        while not mselList_It.isDone():
            transform = mselList_It.getDagPath()
            transform_mfn = OpenMaya2.MFnTransform(transform)

            for i in range(transform_mfn.attributeCount()):
                transform_attr = transform_mfn.attribute(i)  # MObject
                transform_plug = transform_mfn.findPlug(transform_attr, True).info  # conect a plug
                # review: recollect float attributes, int, and boolean. better only boolean
                if transform_plug == '%s.%s' % (transform, attr) and transform_attr.apiType() == type:
                    transformReturn.append(pm.PyNode(transform))
                    break

            mselList_It.next()

        return transformReturn


    @staticmethod
    def listAttrTypes():
        mSelList = OpenMaya2.MGlobal.getActiveSelectionList()

        mSelIt = OpenMaya2.MItSelectionList(mSelList)

        while not mSelIt.isDone():

            transform = mSelIt.getDependNode()
            mfnTransform = OpenMaya2.MFnDependencyNode(transform)

            print transform

            for i in range(mfnTransform.attributeCount()):
                transformAttr = mfnTransform.attribute(i)
                transformAttr_plug = mfnTransform.findPlug(transformAttr, True)
                print ('%s is type: %s' % (transformAttr_plug.info, transformAttr.apiTypeStr))

            mSelIt.next()


    @staticmethod
    def getSingleSourceObjectFromPlug(plug):
        """
            plug: attribute MObject
            Returns: MObject
        """
        if plug.isConnected():
            # Get connected input plugs
            connections = OpenMaya2.MPlugArray()
            plug.connectedTo(connections, True, False)

            # Find input transform
            if connections.length() == 1:
                return connections[0].node()

        return None


    @staticmethod
    def getFnFromPlug(plug, fnType):
        """
            plug: attribute MObject
            fnType: type object
            Returns: dagPath of object type
        """
        node = APIHelp.getSingleSourceObjectFromPlug(plug)

        # Get Fn from a DAG path to get the world transformations correctly
        if node is not None:
            path = OpenMaya2.MDagPath()
            trFn = OpenMaya2.MFnDagNode(node)
            trFn.getPath(path)

            path.extendToShape()

            if path.node().hasFn(fnType):
                return path

        return None

#######################
##Deformer operations##
#######################
class DeformerOp:

    class WeightsOP:
        # TODO: work with BS targets
        def __init__(self):
            # weights buffer
            self._weights = None
            # data to calculate symmetric weights, with barycentric coords
            self._symetryWeights = None
            # list with symmetric index vertex, 3 vertices for each vertex, to apply correct the barycentric weights
            self._symetryID = None


        def shrinkWeight(self):
            """
            shrink the vertex weight values
            :return:
            """
            for i in range(self._weights.length()):
                self._weights[i] = self._weights[i] * self._weights[i]


        def inverValues(self):
            """
            Invert vertex weight values
            :return:
            """
            for i in range(self._weights.length()):
                self._weights[i] = 1.0 - self._weights[i]


        def setSymetryData(self, mesh, axis="x"):
            """
            set symmetry data
            :param mesh: Base mesh to set the symmetry
            :param axis:
            """
            print "__StartSymetry__"
            self._symetryWeights, self._symetryID = MeshOp.barycentricSym(mesh, axis)
            print "__EndSymetry__"


        def mirrorWeights(self):
            """
            Mirror the data in BSWeights
            :param BSNode:
            :return:
            """
            oldWeights = OpenMaya.MFloatArray(self._weights)
            for i in range(oldWeights.length()):
                newWeight = 0.0
                for j, axis in enumerate("xyz"):
                    newWeight += getattr(self._symetryWeights[i], axis) * oldWeights[self._symetryID[i * 3 + j]]

                self._weights[i] = newWeight


        def setWeights(self, node):
            """
            Method to apply the current weights in the buffer
            :param node:
            :return:
            """
            # check type
            node = pm.PyNode(node) if isinstance(node, str) else node

            if isinstance(node, pm.nodetypes.BlendShape):
                self._setWeights_BS(node)

            else:
                self._setWeights_DEF(node)


        def getWeights(self, node):
            """
            Method to get the current weights in the buffer
            :param node:
            :return:
            """
            # check type
            node = pm.PyNode(node) if isinstance(node, str) else node

            if isinstance(node, pm.nodetypes.BlendShape):
                self._getWeights_BS(node)

            else:
                self._getWeights_DEF(node)


        def _setWeights_BS(self, BSNode):
            """
            Set the Blend shape weights with the float array values
            :param BSNode:
            :return:
            """
            arraySize, weightAttr = self._setGetCommon(BSNode)

            if arraySize != self._weights.length():
                logger.info("mFloatArray do not has the correct size")
                return

            for i in range(arraySize):
                weightAttr[i].set(self._weights[i])


        def _getWeights_BS(self, BSNode):
            """
            Get the blend shape node weights per vertex
            :param BSNode:
            :return:
            """
            arraySize, weightAttr = self._setGetCommon_BS(BSNode)

            # set the array with the total of points, mFloatArray is faster
            self._weights = OpenMaya.MFloatArray(arraySize, 0.0)

            for i in range(arraySize):
                self._weights.set(weightAttr[i].get(), i)


        def _setGetCommon_BS(self, BSNode):
            """
            Common between get and set bs weights
            must call plug_weight.destructHandle(dataHandle) at the end
            :param BSNode (str):
            :return:
            """
            # get total vertex in mesh
            mesh = pm.PyNode(str(BSNode)).outputGeometry.outputs()[0].getShape()
            arraySize = mesh.numVertices()
            weightAttr = pm.PyNode('%s.inputTarget[0].baseWeights' % BSNode)

            return arraySize, weightAttr


        def _setWeights_DEF(self, node):
            """
            set weights for deformer objects no blend shape
            :param node:
            :return:
            """
            weightGeometryFilter, arraySize, components, dagPath = self._setGetCommon_DEF(node)

            weightGeometryFilter.setWeight(dagPath, components, self._weights)


        def _getWeights_DEF(self, node):
            """
            Get the weights map of a deformer
            :param node:
            :return:
            """
            weightGeometryFilter, arraySize, components, dagPath = self._setGetCommon_DEF(node)

            self._weights = OpenMaya.MFloatArray(arraySize, 0.0)
            weightGeometryFilter.getWeights(0, components, self._weights)  # review documentation


        def _setGetCommon_DEF(self, node):
            """
            Common Operations between get ans set for deformers
            :param node:
            :return:
            """
            # get cluster
            mSelection = OpenMaya.MSelectionList()
            mSelection.add(str(node))
            # deformer
            deformerMObject = OpenMaya.MObject()
            mSelection.getDependNode(0, deformerMObject)

            # weight mfn
            weightGeometryFilter = OpenMayaAnim.MFnWeightGeometryFilter(deformerMObject)
            membersSelList = OpenMaya.MSelectionList()
            fnSet = OpenMaya.MFnSet(weightGeometryFilter.deformerSet())  # set components affected
            fnSet.getMembers(membersSelList, False)  # add to selection list
            dagPathComponents = OpenMaya.MDagPath()
            components = OpenMaya.MObject()
            membersSelList.getDagPath(0, dagPathComponents, components)  # first element deformer set
            # get original weights
            arraySize = OpenMaya.MFnMesh(dagPathComponents).numVertices()

            return weightGeometryFilter, arraySize, components, dagPathComponents


    @staticmethod
    def smoothDeformerWeights(deformer):
        """
        smooth deformer weights.
        :param deformer(str): Deformer name
        """
        mSelection = OpenMaya.MSelectionList()
        mSelection.add(deformer)
        # deformer
        deformerMObject = OpenMaya.MObject()
        mSelection.getDependNode(0, deformerMObject)

        # documentation: https://groups.google.com/forum/#!topic/python_inside_maya/E7QirW4Z0Nw
        # weight mfn
        weightGeometryFilter = OpenMayaAnim.MFnWeightGeometryFilter(deformerMObject)
        membersSelList = OpenMaya.MSelectionList()
        fnSet = OpenMaya.MFnSet(weightGeometryFilter.deformerSet())  # set components affected
        fnSet.getMembers(membersSelList, False)  # add to selection list
        dagPathComponents = OpenMaya.MDagPath()
        components = OpenMaya.MObject()
        membersSelList.getDagPath(0, dagPathComponents, components)  # first element deformer set

        # get original weights
        originalWeight = OpenMaya.MFloatArray()
        weightGeometryFilter.getWeights(0, components, originalWeight)

        # mesh
        meshVertIt = OpenMaya.MItMeshVertex(dagPathComponents)

        newWeights = OpenMaya.MFloatArray()
        # calculate new weights
        while not meshVertIt.isDone():
            index = meshVertIt.index()
            connectedVertices = OpenMaya.MIntArray()
            meshVertIt.getConnectedVertices(connectedVertices)

            averageValue = originalWeight[index]
            for vertex in connectedVertices:
                averageValue += originalWeight[vertex]

            newWeights.append(averageValue / (connectedVertices.length() + 1))

            meshVertIt.next()

        # set new weights
        weightGeometryFilter.setWeight(dagPathComponents, components, newWeights)


    @staticmethod
    def setWireDeformer(joints, mesh=None, nameInfo=None, curve=None, weights=None):
        """
        Create a curve and wire deformer using joint position as reference
        :param joints(pm or str): joints
            mesh(list): list of meshes wire will affect
        :return: wire deformer and created curve
        nameInfo: characterName_zone_side
        """
        # create pm objects from list
        joints = [pm.PyNode(joint) if isinstance(joint, str) else joint for joint in joints]

        # get points
        points = [joint.getTranslation('world') for joint in joints]
        logger.debug('Wire Deformer curve points: %s' % points)

        # If curve arg is None, create a two point curve
        if not curve:
            curve = pm.curve(ep=[points[0], points[-1]], d=2, name=str(nameInfo) + '_wire_curve')
            # adjust curve points
            snapCurveToPoints(joints, curve)

        # if not mesh arg, get a random mesh trough the skinCluster
        if not mesh:
            mesh = DeformerOp.getSkinedMeshFromJoint(joints[0]).pop()
        else:
            # check type node
            if isinstance(mesh, str):
                mesh = pm.PyNode(mesh)
            if isinstance(mesh, pm.nodetypes.Transform):
                mesh = mesh.getShape()

        # get affected vertex
        affectedVertex = vertexIntoCurveCilinder(str(mesh), str(curve.getShape()), 15, .05, .98)

        # create wire deformer
        wire, wireCurve = pm.wire(mesh, gw=False, w=curve, dds=(0, 40))
        logger.debug('wire curve: %s' % wireCurve)
        pm.percent(wire, mesh, v=0)
        for index in affectedVertex:
            pm.percent(wire, mesh.vtx[index], v=1)

        # copyDeformerWeights  ->  command for copy, mirror deformer weights
        # smooth weights
        for i in range(4):
            DeformerOp.smoothDeformerWeights(str(wire))

        return wire, curve


    @staticmethod
    def latticeBendDeformer(lattice, controller=None):
        """
        connect a bend deformer to a lattice, and the necessary nodes.
        Controller should have transforms to zero.
        :param lattice: lattice transform or shape
        :param controller: Controller for the system
        :return(list): Transform nodes created in the function:  scaleGrp, referenceBase, referenceController, bendTransform,
        :return: controllerRoot
        """
        # TODO: test with non world aligned lattices
        # TODO: class?
        # check data type
        # check lattice type data
        if isinstance(lattice, str):
            lattice = pm.PyNode(lattice)
        if isinstance(lattice, pm.nodetypes.Transform):
            lattice = lattice.getShape()

        # check controller type
        if isinstance(controller, str):
            controller = pm.PyNode(controller)
        if not isinstance(controller, pm.nodetypes.Transform):
            logger.info('controller must be a transform node')
            return

        latticeTransform = lattice.getTransform()
        # check lattice visibility, important to query correctly the bbox
        if not latticeTransform.visibility.get():
            latticeTransform.visibility.set(True)

        # lattice bbox
        latticeTransform = lattice.getTransform()
        latBbox = latticeTransform.boundingBox()
        logger.debug('LatBboc: %s' % latBbox)

        # Util transform  data
        centerPoint = (latBbox[0] + latBbox[1]) / 2
        logger.debug('Lattice center point: %s, %s' % (centerPoint, type(centerPoint)))
        # min and max centered points
        minPoint = pm.datatypes.Point(centerPoint[0], latBbox[0][1], centerPoint[2])
        maxPoint = pm.datatypes.Point(centerPoint[0], latBbox[1][1], centerPoint[2])
        latHigh = latBbox[1][1] - latBbox[0][1]

        # reposition controller
        controller.setTranslation(maxPoint, 'world')
        # root the controller
        controllerRoot = createRoots([controller])[0]

        # create bend deformer
        # review, get some warnings here, maybe cmds is a better option
        bend, bendTransform = cmds.nonLinear(str(lattice), type='bend', lowBound=-1, curvature=0)
        bendTransform = pm.PyNode(bendTransform)
        bendTransform.setTranslation(minPoint, 'world')
        cmds.setAttr('%s.lowBound' % (bend), 0)
        cmds.setAttr('%s.highBound' % (bend), 1)
        # set scale lattice
        bendTransform.scale.set([latHigh, latHigh, latHigh])

        ## create nodes ##
        distanceBettween = pm.createNode('distanceBetween')
        distanceBettween.point2.set([0, 0, 0])
        # don't connect y component
        for axis in ('X', 'Z'):
            controller.attr('translate%s' % axis).connect(distanceBettween.attr('point1%s' % axis))

        # condition, to avoid vector with length 0
        condition = pm.createNode('condition')
        distanceBettween.distance.connect(condition.firstTerm)
        conditionAxis = ['R', 'B']
        for i, axis in enumerate(['X', 'Z']):
            controller.attr('translate%s' % axis).connect(condition.attr('colorIfFalse%s' % conditionAxis[i]))

        condition.colorIfFalseG.set(0)
        condition.colorIfTrue.set([0.001, 0, 0])

        # normalizeVector
        normalize = pm.createNode('vectorProduct')
        normalize.operation.set(0)
        normalize.normalizeOutput.set(True)  # normalized
        condition.outColor.connect(normalize.input1)
        # find vector z, use cross product
        crossProduct = pm.createNode('vectorProduct')
        crossProduct.normalizeOutput.set(True)  # normalize
        crossProduct.operation.set(2)
        normalize.output.connect(crossProduct.input1)
        crossProduct.input2.set([0, 1, 0])
        # create fourByFour matrix
        matrix = pm.createNode('fourByFourMatrix')
        # vector X
        for i, axis in enumerate(['X', 'Y', 'Z']):
            normalize.attr('output%s' % axis).connect(matrix.attr('in0%s' % i))
        # vector Z
        for i, axis in enumerate(['X', 'Y', 'Z']):
            crossProduct.attr('output%s' % axis).connect(matrix.attr('in2%s' % i))

        # decompose Matrix
        decomposeMatrix = pm.createNode('decomposeMatrix')
        matrix.output.connect(decomposeMatrix.inputMatrix)
        # connect rotation
        decomposeMatrix.outputRotate.connect(bendTransform.rotate)

        ## curvature ##
        decomposeMatrixController = pm.createNode('decomposeMatrix')
        controller.worldMatrix.connect(decomposeMatrixController.inputMatrix)
        # transformNodes
        referenceController = pm.group(empty=True, name='%s_ctr_ref' % str(latticeTransform))
        pm.xform(referenceController, ws=True, m=pm.xform(controller, q=True, ws=True, m=True))
        referenceBase = pm.group(empty=True, name='%s_base_ref' % str(latticeTransform))
        referenceBase.setTranslation(minPoint, 'world')
        # ref Controller
        RefControllerDecMatr = pm.createNode('decomposeMatrix')
        referenceController.worldMatrix.connect(RefControllerDecMatr.inputMatrix)
        # base
        refBaseDecMatr = pm.createNode('decomposeMatrix')
        referenceBase.worldMatrix.connect(refBaseDecMatr.inputMatrix)
        # firstVector
        vector1 = pm.createNode('plusMinusAverage')
        vector1.operation.set(2)  # substract
        decomposeMatrixController.outputTranslate.connect(vector1.input3D[0])
        refBaseDecMatr.outputTranslate.connect(vector1.input3D[1])
        # second vector
        vector2 = pm.createNode('plusMinusAverage')
        vector2.operation.set(2)  # substract
        RefControllerDecMatr.outputTranslate.connect(vector2.input3D[0])
        refBaseDecMatr.outputTranslate.connect(vector2.input3D[1])
        # calculate angle
        angleBetween = pm.createNode('angleBetween')
        vector1.output3D.connect(angleBetween.vector1)
        vector2.output3D.connect(angleBetween.vector2)
        # connect to bend
        cmds.connectAttr('%s.angle' % (str(angleBetween)), '%s.curvature' % bend)

        ## scale system ##
        scaleGrp = pm.group(empty=True, name='%s_scale_grp' % str(latticeTransform))
        scaleGrp.setTranslation(minPoint, 'world')
        scaleGrp.addChild(latticeTransform)
        # node connection
        # distance between controller and base lattice
        distanceBettween = pm.createNode('distanceBetween')
        controller.worldMatrix.connect(distanceBettween.inMatrix1)
        referenceBase.worldMatrix.connect(distanceBettween.inMatrix2)
        # distance between controller REFERENCE and base lattice
        distanceReference = pm.createNode('distanceBetween')
        referenceController.worldMatrix.connect(distanceReference.inMatrix1)
        referenceBase.worldMatrix.connect(distanceReference.inMatrix2)
        # divide by the original length
        multiplyDivide = pm.createNode('multiplyDivide')
        multiplyDivide.operation.set(2)  # set to divide
        # connect distances
        distanceBettween.distance.connect(multiplyDivide.input1X)
        distanceReference.distance.connect(multiplyDivide.input2X)
        # get inverse
        inverse = pm.createNode('multiplyDivide')
        inverse.operation.set(2)  # divide
        inverse.input1X.set(1)
        multiplyDivide.outputX.connect(inverse.input2X)
        # connect result to scale group
        multiplyDivide.outputX.connect(scaleGrp.scaleY)
        for axis in ('X', 'Z'):
            inverse.outputX.connect(scaleGrp.attr('scale%s' % axis))

        # lock and hide attr
        lockAndHideAttr(controller, False, True, True)

        return [scaleGrp, referenceBase, referenceController, bendTransform, controllerRoot]


    @staticmethod
    def addToDeformer(deformer, mesh, source=None):
        # TODO: move to ARCore necessary to
        # documentation: https://groups.google.com/forum/#!topic/python_inside_maya/E7QirW4Z0Nw
        # documentation: https://help.autodesk.com/view/MAYAUL/2018/ENU/?guid=__cpp_ref_class_m_fn_set_html  # mfnSet
        # documentation: https://help.autodesk.com/view/MAYAUL/2018/ENU/?guid=__cpp_ref_class_m_fn_weight_geometry_filter_html  # geometryFilter
        """
        Add a mesh to the deformer, and copy weights between the new mesh and the existent mesh in the deformer
        :param deformer(str): deformer name
        :param mesh2(str): mesh shape where copy weights
        :param source (str): mesh with weights
        :return:
        """
        # check if is pymel node, if it is, convert to str
        deformer = str(deformer) if isinstance(deformer, pm.general.PyNode) else deformer
        mesh = str(mesh) if isinstance(mesh, pm.general.PyNode) else mesh

        # get cluster
        mSelection = OpenMaya.MSelectionList()
        mSelection.add(deformer)
        mSelection.add(mesh)
        # deformer
        deformerMObject = OpenMaya.MObject()
        mSelection.getDependNode(0, deformerMObject)

        # weight mfn
        weightGeometryFilter = OpenMayaAnim.MFnWeightGeometryFilter(deformerMObject)
        membersSelList = OpenMaya.MSelectionList()
        fnSet = OpenMaya.MFnSet(weightGeometryFilter.deformerSet())  # set components affected
        fnSet.getMembers(membersSelList, False)  # add to selection list
        dagPathComponents = OpenMaya.MDagPath()
        components = OpenMaya.MObject()
        memberSelLength = membersSelList.length()  # get the last member, it should be the first object deformed
        if source:
            for i in range(memberSelLength):
                membersSelList.getDagPath(i, dagPathComponents, components)  # first element deformer set
                if dagPathComponents.partialPathName() == source:
                    print "Mesh with weights: %s" % dagPathComponents.partialPathName()
                    break
        else:
            membersSelList.getDagPath(memberSelLength-1, dagPathComponents, components)  # first element deformer set

        print "Mesh %s" % dagPathComponents.partialPathName()
        # get original weights0
        originalWeight = OpenMaya.MFloatArray()
        weightGeometryFilter.getWeights(0, components, originalWeight)  # review documentation

        # ## test components
        # logger.debug("member set list: %s" % membersSelList.length())
        # logger.debug("reference object: %s" % dagPathComponents.fullPathName())
        # return

        # get target mfn and all point positions
        targetDPath = OpenMaya.MDagPath()
        mSelection.getDagPath(1, targetDPath)
        if targetDPath.apiType() is OpenMaya.MFn.kTransform:
            targetDPath.extendToShape()  # if is ktransform type. get the shape
        # target It
        targetIt = OpenMaya.MItMeshVertex(targetDPath)

        # deformer vertex iterator
        sourceVertIt = OpenMaya.MItMeshVertex(dagPathComponents, components)
        sourceMFn = OpenMaya.MFnMesh(dagPathComponents)
        # list index on set fn
        sourceVertexId = OpenMaya.MIntArray()
        while not sourceVertIt.isDone():
            sourceVertexId.append(sourceVertIt.index())
            sourceVertIt.next()

        sourceVertIt.reset()
        logger.debug('source vertex id: %s' % sourceVertexId)

        targetDeformVId = OpenMaya.MIntArray()
        targetSelList = OpenMaya.MSelectionList()
        newWeights = OpenMaya.MFloatArray()
        lastLength = 0  # useful to find valid vertex
        # closest vertex from target to source
        # review, optimize
        while not targetIt.isDone():
            TVid = targetIt.index()
            TargetPoint = targetIt.position()
            closestPoint = OpenMaya.MPoint()
            # util
            util = OpenMaya.MScriptUtil()
            ptr = util.asIntPtr()
            sourceMFn.getClosestPoint(TargetPoint, closestPoint, OpenMaya.MSpace.kObject, ptr)  # review kworld
            polyId = util.getInt(ptr)

            # get vertices from face id
            vertexId = OpenMaya.MIntArray()
            # gives the vertex in non clock direction
            sourceMFn.getPolygonVertices(polyId, vertexId)
            vertexLength = vertexId.length()
            weightList=[]
            totalArea = 0
            areaList=[]
            totalWeight = 0
            # polygonArea
            # sourceVertIt.setIndex(polyId)
            # iterate over the face vertex
            # check if any vertex is in the list of source vertex
            # TODO: review calculations, and try to optimize
            if set(vertexId) & set(sourceVertexId):  # & intersection
                for i, Vid in enumerate(vertexId):
                    # check first if any vertex is in the list
                    # calculate relative weight.
                    DistPoint = OpenMaya.MPoint()
                    sourceMFn.getPoint(Vid, DistPoint)  # get weighted vertex position
                    DistVector = OpenMaya.MVector(closestPoint - DistPoint)
                    vectorU = OpenMaya.MPoint()  # vectorA
                    sourceMFn.getPoint(vertexId[i-1], vectorU)
                    vectorV = OpenMaya.MPoint()  # vertorB
                    sourceMFn.getPoint(vertexId[(i+1) % vertexLength], vectorV)
                    # construct barycentricc vectors
                    # documentation: http://blackpawn.com/texts/pointinpoly/
                    vectorU = OpenMaya.MVector(vectorU - DistPoint)
                    vectorV = OpenMaya.MVector(vectorV - DistPoint)

                    # Barycentric coords
                    u, v = VectorMath.barycentricCoords(vectorU, vectorV, DistVector)

                    areaVector = (vectorU*(1-u) ^ vectorV*(1-v)).length()
                    totalArea += areaVector
                    areaList.append(areaVector)

                    # get wheights
                    if Vid in sourceVertexId:
                        weightIndex = list(sourceVertexId).index(Vid)  # get the vertex list index, valid for the weight list
                        sourceWeight = originalWeight[weightIndex]  # get weight value from the list
                    else:
                        sourceWeight = 0
                    weightList.append(sourceWeight)

                    # save valid vertex index. only once.
                    if not TVid in targetDeformVId:
                        targetDeformVId.append(TVid)
                        # save components in a selection list. this way we can add it to our set
                        targetSelList.add(targetDPath, targetIt.currentItem())

            # now calculate and assign weight value
            newLength = targetDeformVId.length()
            if lastLength < newLength:
                weightTarget = 0
                for i, area in enumerate(areaList):
                    weightTarget += (area/totalArea)*weightList[i]

                newWeights.append(weightTarget)
                lastLength = newLength

            targetIt.next()

        # add to mfnSet
        fnSet.addMembers(targetSelList)
        PaintSelList = OpenMaya.MSelectionList()
        fnSet.getMembers(PaintSelList, False)

        # calculate weights
        # get from selection list
        components = OpenMaya.MObject()
        targetNewWDPath = OpenMaya.MDagPath()
        for i in range(PaintSelList.length()):
            # check we have desired dagpath
            PaintSelList.getDagPath(i, targetNewWDPath, components)
            if targetNewWDPath.partialPathName() == targetDPath.partialPathName():
                break
        logger.debug(newWeights)
        weightGeometryFilter.setWeight(targetNewWDPath, components, newWeights)


    @staticmethod
    def getSkinedMeshFromJoint(joint):
        """
        Find meshes affected by the joint
        :param joint (pm or str): joint
        :return (set): Meshes affected by the joint
        """
        # create pm objects from list
        joint = pm.PyNode(joint) if isinstance(joint, str) else joint
        # find skin clusters
        skinClusterLst = set(joint.listConnections(type='skinCluster'))

        meshes = []
        for skin in skinClusterLst:
            meshes += skin.getGeometry()

        return set(meshes)


    @staticmethod
    def mirrorCluster(cluster, symmetry="x"):
        """
        create a cluster, symmetric to the input cluster. and symmetrize weights
        :param cluster(str or pm): cluster deformer node
        :return: symCluster, symClsterTrn, symClstrShp
        """
        # check type
        cluster = pm.PyNode(cluster) if isinstance(cluster, str) else cluster
        clusterTrn = cluster.matrix.inputs()[0]  # get clster trans
        clusterShp = clusterTrn.getShape()  # get cluster Shp

        # create a invert vector
        symVec = pm.datatypes.Vector([1,1,1])
        for axis in "xyz":
            if axis == symmetry:
                setattr(symVec, axis, -1)
                break

        print symVec.x, symVec.y, symVec.z

        defMesh = cluster.getGeometry()[0]

        # get weiths from original cluster, and mirror it
        weights = DeformerOp.WeightsOP()
        weights.setSymetryData(defMesh, "x")
        weights.getWeights(cluster)
        weights.mirrorWeights()

        symCluster, symClsterTrn = pm.cluster(defMesh) # fixme
        weights.setWeights(symCluster)

        # deformer order
        pm.reorderDeformers(cluster, symCluster, defMesh)

        symClstrShp = symClsterTrn.getShape()

        # set origin, origin is the visual shape in the maya visor
        origin = pm.datatypes.Vector(clusterShp.origin.get())
        for axis in "xyz":
            setattr(origin, axis, getattr(origin, axis) * getattr(symVec, axis))
        # set origin
        symClstrShp.origin.set(origin)

        # apply pivots symmetry
        for attr in ["rotatePivot", "scalePivot"]:
            val = pm.datatypes.Vector(clusterTrn.attr(attr).get())
            for axis in "xyz":
                setattr(val, axis, getattr(val, axis) * getattr(symVec, axis))
            symClsterTrn.attr(attr).set(val)

        # set relative
        symCluster.relative.set(cluster.relative.get())

        # create root
        createRoots(symClsterTrn)
        # return cluster and dag nodes
        return symCluster, symClsterTrn, symClstrShp


def vertexIntoCurveCilinder(mesh, curve, distance, minParam=0, maxParam=1):
    """
    Return a list of vertex index inside cilinder defined by a curve
    :param mesh(str): mesh shape
    :param curve(str): curve shape
    :param distance(float):
    :return: List with vertex indexes
    """
    # use the API, Faster for this type of operations
    mSelection = OpenMaya.MSelectionList()
    mSelection.add(mesh)
    mSelection.add(curve)

    # MDagObject to query worldSpace deforms
    # mesh
    meshDagPath = OpenMaya.MDagPath()
    mSelection.getDagPath(0, meshDagPath)
    meshVertIt = OpenMaya.MItMeshVertex(meshDagPath)  # vertexIterator
    # curve
    curveDagPath = OpenMaya.MDagPath()
    mSelection.getDagPath(1, curveDagPath)
    curveMFn = OpenMaya.MFnNurbsCurve(curveDagPath)

    # minParam MaxParam adjust to maxValue of the curve
    maxParam = cmds.getAttr('%s.maxValue' % curve)*maxParam
    minParam = cmds.getAttr('%s.maxValue' % curve)*minParam + cmds.getAttr('%s.minValue' % curve)

    # mscriptUtil
    util = OpenMaya.MScriptUtil()
    vertexIndexes = []  # store vertex indexes
    while not meshVertIt.isDone():
        # store vertex position
        vertexPosition = meshVertIt.position(OpenMaya.MSpace.kWorld)
        # point on curve
        ptr = util.asDoublePtr()
        curveMFn.closestPoint(vertexPosition, ptr, 0.1, OpenMaya.MSpace.kWorld)  # review param (False, ptr)
        param = util.getDouble(ptr)
        # param control
        param = max(minParam, min(maxParam, param))

        # recalculate from param
        pointCurve = OpenMaya.MPoint()
        curveMFn.getPointAtParam(param, pointCurve)

        # define vector
        vertexVector = OpenMaya.MVector(vertexPosition-pointCurve)
        # check distance from the curve
        if vertexVector.length() < distance:
            tangent = curveMFn.tangent(param, OpenMaya.MSpace.kWorld)  # get param tangent
            # dot product
            dotProduct = vertexVector*tangent
            # let some precision interval
            if not (dotProduct > 0.1 or dotProduct < -0.1):
                vertexIndexes.append(meshVertIt.index())

        meshVertIt.next()

    return vertexIndexes


def transformDriveNurbObjectCV(nurbObject, follow=False):
    """
    Connect transformations to each Curve Vertex point
    :param curve(str or pm):
    :return (list): list with created transformations
    """
    # check curve type data
    if isinstance(nurbObject, str):
        nurbObject = pm.PyNode(nurbObject)
    if isinstance(nurbObject, pm.nodetypes.Transform):
        nurbObject = nurbObject.getShape()

    baseName = ('%s_cv') % str(nurbObject.getTransform())

    transforms = []
    for n, point in enumerate(nurbObject.getCVs()):
        transform = pm.group(empty=True, name='%s%s_grp' % (baseName, n))
        transform.setTranslation(point)
        decomposeMatrix = pm.createNode('decomposeMatrix')
        transform.worldMatrix[0].connect(decomposeMatrix.inputMatrix)
        decomposeMatrix.outputTranslate.connect(nurbObject.controlPoints[n])

        if isinstance(nurbObject, pm.nodetypes.NurbsCurve) and follow:
            closest = nurbObject.closestPoint(transform.getTranslation("world"), tolerance=0.1, space="world")
            param = nurbObject.getParamAtPoint(closest, "world")

            tangent = nurbObject.tangent(min(max(nurbObject.minValue.get()+0.0001, param),nurbObject.maxValue.get()-0.0001))
            tangent.normalize()
            normal = nurbObject.normal(min(max(nurbObject.minValue.get()+0.0001, param),nurbObject.maxValue.get()-0.0001))
            normal.normalize()
            biNormal = tangent ^ normal
            biNormal.normalize()

            translation = transform.getTranslation("world")
            matrix = pm.datatypes.Matrix([tangent.x,tangent.y, tangent.z, 0],
                                         [biNormal.x, biNormal.y, biNormal.z, 0],
                                         [normal.x, normal.y, normal.z, 0],
                                         [translation.x, translation.y, translation.z, 1])

            print "param"

            transform.setMatrix(matrix)

        transforms.append(transform)

    return transforms


def jointChain(length=None, joints=10, curve=None):
    """
    create a joint chain
    :param distance(float): length of the chain, if curve arg is given, this param can be None
    :param joints(int): number of joints
    :param curve(str or pm): if curve, adapt joints to curve
    :return: joint list
    """
    # to avoid errors clear selection
    pm.select(cl=True)

    jointsList = []  # to store joints

    # if curve arg
    if curve:
        # check type
        if isinstance(curve, str):
            curve = pm.PyNode(curve)
        if isinstance(curve, pm.nodetypes.Transform):
            curve = curve.getShape()

        # dup the curve and rebuilt it, smoother results
        curveDup = curve.duplicate()[0]
        curveDup = curveDup.getShape()
        pm.rebuildCurve(curveDup, ch=False, rpo=True, rt=False, end=True, kr=False, kep=True,
                        kt=False, s=curveDup.numCVs(), d=2, tol=0.01)

        # get max param value of the curve
        maxValue = curveDup.maxValue.get()
        incrValue = maxValue/(joints-1)  # distance increment per joint
        for i in range(joints+1):
            # create joint
            if i < joints:
                pm.select(cl=True)
                joint = pm.createNode('joint')
                joint.setTranslation(curveDup.getPointAtParam(incrValue * i, 'world'), 'world')
                pm.select(cl=True)
            if jointsList:
                # first construct matrix
                if i < joints:
                    vectorX = pm.datatypes.Vector(joint.getTranslation('world') - jointsList[-1].getTranslation('world'))
                    vectorX.normalize()
                else:
                    vectorX = curveDup.tangent(incrValue*(i-1), 'world')

                # if the curve do not has curvature, normal method will give us an error
                try:
                    vectorY = curveDup.normal(incrValue*(i-1), 'world')
                except:
                    # if it is the case, construct a basic vector
                    vectorY = pm.datatypes.Vector([0,1,0])
                    # while dot != 0 the vector isn't perpendicular
                    if vectorX * vectorY != 0:
                        # so we force a zero dot. dot formula: v1.x*v2.x + v1.y*v2.y + v1.z*v2.z
                        logger.debug('vectorY no perpendicular '+str(vectorY))
                        vectorY.z = - (vectorX.y*vectorY.y / vectorX.z)

                    # normalize vector
                    vectorY.normalize()

                vectorZ = vectorX ^ vectorY  # cross product
                vectorZ.normalize()
                # recalculate Y
                vectorY =vectorZ ^ vectorX
                vectorY.normalize()

                # get position
                position = curveDup.getPointAtParam(incrValue*(i-1), space='world')

                # apply matrix
                pm.xform(jointsList[-1], ws=True, m=[vectorX.x, vectorX.y, vectorX.z, 0,
                                            vectorY.x, vectorY.y, vectorY.z, 0,
                                            vectorZ.x, vectorZ.y, vectorZ.z, 0,
                                            position.x, position.y, position.z, 1])

                # freeze rotation
                pm.makeIdentity(jointsList[-1], apply=True, t=False, r=True, s=False, n=False, pn=False)

            # append new joint
            if i < joints:
                jointsList.append(joint)

        # construct hierarchy
        for i in range(joints-1):
            jointsList[i].addChild(jointsList[i+1])

        # delete duplicated curve
        pm.delete(curveDup.getTransform())

    # if not curve arg
    elif length:
        # distance between joints
        distanceBetween = length / joints
        for i in range(joints):
            joint = pm.joint(p=[distanceBetween*i,0,0])
            # append to list
            jointsList.append(joint)
        pm.select(cl=True)  # clear selection, to avoid possible errors with more chains

    return jointsList


####################################
##Nurbs surface or curve Operation##
####################################
def curveToSurface(curve, width=5.0, steps=10):
    """
    Create a surface from a nurbsCurve, using a loft node.
    Use BBox to select one axis and move cvs of the curves
    :param curve(pm or str): curve to generate loft
    :return(tranform node): loft surface between curves
    """
    # check types
    if isinstance(curve, str):
        curve = pm.PyNode(curve)
    if isinstance(curve, pm.nodetypes.Transform):
        curve = curve.getShape()

    curveTransform = curve.getTransform()

    # detect thinnest side using a bbox
    bbox = curve.boundingBox()
    bboxDict={}
    for i, axis in enumerate('xyz'):  # priority to z axis
        bboxDict[axis] = abs(bbox[0][i] - bbox[1][i])

    minVal = min(bboxDict.values())
    minAxis = bboxDict.keys()[bboxDict.values().index(minVal)]

    for axis in 'xz':
        if minAxis == 'y' and minVal == bboxDict[axis]:
            minAxis = axis

    # duplicate curve
    dupCurve1 = curveTransform.duplicate()[0]
    dupCurve1 = dupCurve1.getShape()
    dupCurve2 = curveTransform.duplicate()[0]
    dupCurve2 = dupCurve2.getShape()

    # edit points
    newPoint = pm.datatypes.Point(0, 0, 0)
    setattr(newPoint, minAxis, width / 2.0)
    # edit cvPoints
    for j, curv in enumerate([dupCurve1, dupCurve2]):
        # rebuildCurve
        pm.rebuildCurve(curv,ch=False, rpo=True, rt=False, end=True, kr=False, kep=True, kt=False, s=steps, d=2, tol=0.01)
        sign = -1 if j%2 else 1  # increment positive or negative
        for i, CvPoint in enumerate(curv.getCVs('object')):
            curv.setCV(i, CvPoint + (newPoint*sign), 'object')
            curv.updateCurve()

    # create loft
    loft = pm.loft(dupCurve1, dupCurve2, ch=False, u=True, c=False, ar=True, d=2, ss=True,
                   rn=False, po=False, rsn=True)[0]
    pm.delete(dupCurve1.getTransform(), dupCurve2.getTransform())

    return loft


def createCurveFromTransforms(transforms, degree=3):
    """
    create curve from transform list
    :param transforms [list]:
    :return:
    """
    transformPoints = [pm.PyNode(str(transform)).getTranslation('world') for transform in transforms]
    curve = pm.curve(ep=transformPoints, d=degree)

    return curve, curve.getShape()


def squareController(heigh, width, normalAxis= 'x', color=None):
    """
    Create a curve square control with only one shape
    :param heigh:
    :param width:
    :param normal:
    :return:
    """
    # normal plane
    normalPlane = 'xyz'.replace(normalAxis[0], '')
    if len(normalPlane) > 2:
        logger.error('squareController: normalAxis param must be "x" "y" or "z"')
        raise RuntimeError

    # point array, and construct the curve
    widthList = [-width/2.0, width/2.0, width/2.0, -width/2.0]
    heighList = [heigh/2.0, heigh/2.0, -heigh/2.0, -heigh/2.0]
    pointArr = []
    for i in range(len(widthList)+1):
        indx = i % len(widthList)
        point = pm.datatypes.Point(0,0,0)
        setattr(point, normalPlane[0], widthList[indx])
        setattr(point, normalPlane[1], heighList[indx])
        pointArr.append(point)

    # construct the curve using the point array
    sqrController = pm.curve(ep=pointArr, ws=True ,d=1)

    # if color, apply the color on the shape
    if color:
        shape = sqrController.getShape()
        shape.overrideEnabled.set(True)
        shape.overrideColor.set(color)

    return sqrController

class MeshOp():
    """
    Class with static methods to manipulate mesh
    """
    @staticmethod
    def barycentricSym(mesh, axis='x'):
        """
        Return a list with the vertex and their weight with symetrize vertex.
        all in object space
        [Vid,[Vid, W], [Vid, W] ... ]
        :param mesh(str):
        :return:
        """
        # get selection list
        mSel = OpenMaya.MSelectionList()
        mSel.add(str(mesh))

        # get depend node
        mDagPath = OpenMaya.MDagPath()
        mSel.getDagPath(0, mDagPath)

        if mDagPath.apiType() == OpenMaya.MFn.kTransform:
            # if we get the transform, descent to the shape
            mDagPath.extendToShape()
        meshObj = mDagPath.node()

        # mfnMesh
        mFnMesh = OpenMaya.MFnMesh(mDagPath)
        vertexCount = mFnMesh.numVertices()
        #itterator
        mItMesh = OpenMaya.MItMeshVertex(mDagPath)

        # get all points
        vPoints = OpenMaya.MFloatPointArray()
        mFnMesh.getPoints(vPoints)

        # build mesh intersection
        meshPt = OpenMaya.MPointOnMesh()
        meshIntersector = OpenMaya.MMeshIntersector()
        meshIntersector.create(meshObj, OpenMaya.MMatrix.identity)

        # to save info
        # change to python types
        arrayWeights = OpenMaya.MPointArray(vertexCount)  # groups of 3
        arrayIndex = OpenMaya.MIntArray(vertexCount*3)  # every 3 is a new vertex
        #arrayWeights=[]
        #arrayIndex=[]
        # getPolygonTriangleVertices(polygonId, triangleId, vertexList[3](mintArray))
        # return (u >= 0) && (v >= 0) && (u + v < 1) point in the try

        # the fastest way to iterate over a mesh
        #it = 0
        while not mItMesh.isDone():
            vertID = mItMesh.index()
            vertInvPos = mItMesh.position()
            # inverVert.x to find the respective vertex
            setattr(vertInvPos, axis, - getattr(vertInvPos, axis))

            # use intersection to get closest info
            meshIntersector.getClosestPoint(vertInvPos, meshPt, 0.1)
            # get closes point
            closestPoint = meshPt.getPoint()
            faceID = meshPt.faceIndex()
            triID = meshPt.triangleIndex()

            # get vertex of the triangle
            # util
            # seems declaring here the util with an intarray of 3 elments works better
            util = OpenMaya.MScriptUtil(OpenMaya.MIntArray(3))  # storage for 3 elements
            ptr = util.asIntPtr()
            mFnMesh.getPolygonTriangleVertices(faceID, triID, ptr)
            # get ptr info
            vID = [util.getIntArrayItem(ptr, i) for i in range(3)]
            uvL = []

            # get all barycentrics
            for i in range(3):
                uvL.append(VectorMath.barycentricCoords(vPoints[vID[(i+1) % 3]] - vPoints[vID[i]],
                                            vPoints[vID[(i + 2) % 3]] - vPoints[vID[i]],
                                            closestPoint - vPoints[vID[i]]))

            # save here the total area
            totalWeight = 0.0
            weightsList = []
            for i in range(3):
                # ub(c-b)+(b-a)"vB" - vA  // vc(b-c) + (v-a)"vC" - vA
                vA = OpenMaya.MVector(closestPoint - vPoints[vID[i]])  # vector for reference
                vB = (vPoints[vID[(i+2) % 3]] - (vPoints[vID[(i+1) % 3]])) * uvL[(i+1) % 3][0] + (vPoints[vID[(i+1)%3]] - vPoints[vID[i]])
                vB = OpenMaya.MVector(vB) - vA
                vC = (vPoints[vID[(i+1) % 3]] - (vPoints[vID[(i+2) % 3]])) * uvL[(i+2) % 3][1] + (vPoints[vID[(i+2)%3]] - vPoints[vID[i]])
                vC = OpenMaya.MVector(vC) - vA

                weight = (vB ^ vC).length()/2
                totalWeight += weight
                weightsList.append(weight)

            # normalize weights
            for i in range(3):
                weightsList[i] = weightsList[i] / totalWeight

            # save data
            # vertex IDs
            for i in range(3):
                arrayIndex[vertID*3+i] = vID[i]
                #arrayIndex.append(vID[i])

            arrayWeights.set(OpenMaya.MPoint(weightsList[0], weightsList[1], weightsList[2]), vertID)
            #arrayWeights.append([weightsList[0], weightsList[1], weightsList[2]])

            mItMesh.next()

        return arrayWeights, arrayIndex


########################
#Dependency graph utils#
########################
class DGUtils:
    """
    Dependency graph utils, this class exists for organization porpoises
    """
    @staticmethod
    def floatLogic(floatA, floatB, condition):
        """
        create a float logic node
        :param condition: condition type: 0. ==   1. !=
                                         2. <    3. >
                                        4. <=   5. >=
        :return:
        """
        ## check types ##
        floats = [floatA, floatB]
        for i in range(len(floats)):
            if isinstance(floats[i], str):
                floats[i] = pm.PyNode(floats[i])

        nAttr = "AB"
        floatLogic = pm.createNode("floatLogic")
        floatLogic.operation.set(condition)
        for i in range(len(floats)):
            if isinstance(floats[i], float) or isinstance(floats[i], int):
                floatLogic.attr("float%s" % nAttr[i]).set(floats[i])
            else:
                floats[i].connect(floatLogic.attr("float%s" % nAttr[i]))

        return floatLogic.outBool


    @staticmethod
    def colorLogic(colorA, colorB, condition):
        """
        create a color logic node
        :param condition: condition type: 0. ==   1. !=
                                        2. <    3. >
                                        4. <=   5. >=
        :return:
        """
        ## check types ##
        colors = [colorA, colorB]
        for i in range(len(colors)):
            if isinstance(colors[i], str):
                colors[i] = pm.PyNode(colors[i])

        nAttr = "AB"
        colorLogic = pm.createNode("colorLogic")
        colorLogic.operation.set(condition)
        for i in range(len(colors)):
            if isinstance(colors[i], list):
                colorLogic.attr("color%s" % nAttr[i]).set(colors[i])
            else:
                colors[i].connect(colorLogic.attr("color%s" % nAttr[i]))

        colorLogic = colorLogic.outBool

        return colorLogic


    @staticmethod
    def colorCondition(colorA=(0,0,0), colorB=(0,0,0), condition=0, colorTrue=None, colorFalse=None):
        """
        Create a color condition, compare colors.
        :param colorA: logic first arg
        :param colorB: logic second arg
        :param condition: condition type: 0. ==   1. !=
                                          2. <    3. >
                                          4. <=   5. >=
        :param colorTrue colorfalse: alternative values for the float condition node, if none use colorA or colorB
        :return:
        """
        ## check types ##
        colorsBool = [colorTrue, colorFalse]
        for i in range(len(colorsBool)):
            if isinstance(colorsBool[i], str):
                colorsBool[i] = pm.PyNode(colorsBool[i])

        ## func ##
        nAttr = "AB"
        if isinstance(condition, int) or isinstance(condition, float):
            colorLogic = DGUtils.colorLogic(colorA, colorB, condition)
        else:
            colorLogic = condition

        # create condition node
        colorCondition = pm.createNode("colorCondition")
        colorLogic.connect(colorCondition.condition)

        for i in range(len(colorsBool)):
            attrConect = colorsBool[i] if colorsBool[i]  != None else colorLogic.attr("color%s" % nAttr[i])
            if isinstance(attrConect, list):
                colorCondition.attr("color%s" % nAttr[i]).set(attrConect)
            else:
                attrConect.connect(colorCondition.attr("color%s" % nAttr[i]))

        return colorCondition.outColor


    @staticmethod
    def floatCondition(f1=0.0, f2=0.0, condition=0, f1Val=None, f2Val=None):
        """
        :param f1(attr or float): first term
        :param f2 (attr or float): second term
        :param condition (int ot pm): condition type: 0. ==   1. !=
                                                2. <    3. >
                                                4. <=   5. >=  or float logic node

        :param f1Val, f2Val (float): alternative values for the float condition node
        :return:
        """
        ## check types ##
        floats = [f1, f2]
        for i in range(len(floats)):
            if isinstance(floats[i], str):
                floats[i] = pm.PyNode(floats[i])
            elif isinstance(floats[i], int):
                floats[i] = float(floats[i])

        fVal = [f1Val, f2Val]
        for i in range(len(fVal)):
            if isinstance(fVal[i], str):
                fVal[i] = pm.PyNode(fVal[i])
            elif isinstance(fVal[i], int):
                fVal[i] = float(fVal[i])

        ## func ##
        # float 1 / floatA
        nAttr = "AB"
        if isinstance(condition, int) or isinstance(condition, float):
            floatLogic = DGUtils.floatLogic(f1, f2, condition)
        else:
            floatLogic = condition

        ## create float condition node ##
        floatCondition = pm.createNode("floatCondition")
        floatLogic.connect(floatCondition.condition)

        for i in range(len(nAttr)):
            connectAttr = fVal[i] if fVal[i] != None else floats[i]
            if isinstance(connectAttr, float):
                floatCondition.attr("float%s" % nAttr[i]).set(connectAttr)
            else:
                connectAttr.connect(floatCondition.attr("float%s" % nAttr[i]))

        return floatCondition.outFloat


    @staticmethod
    def clamp(input, min=(0,0,0), max=(1,1,1)):
        """
        create a clamp node and return the output value (float3)
        :param min:
        :param max:
        :param input:
        :return:
        """
        # check types
        values = [min, max, input]
        for i in range(len(values)):
            if isinstance(values[i], str):
                values[i] = pm.PyNode(values[i])

        # create node
        clamp = pm.createNode("clamp")

        # min max
        for i, val in enumerate(["min", "max"]):
            if isinstance(values[i], pm.Attribute):
                if values[i].type() == "float3" or values[i].type() == "double3":
                    values[i].connect(clamp.attr(val))
                else:
                    for axis in "RGB":
                        values[i].connect(clamp.attr(val+axis))
            else:
                clamp.attr(val).set(values[i])

        # input
        # TODO: make this like multiplyDivide
        if values[2].type() == "float3" or values[2].type() == "double3":
            values[2].connect(clamp.input)
        else:
            values[2].connect(clamp.inputR)

        return clamp.output


    @staticmethod
    def connectAttributes(driver, driven, attributes, axis):
        """
        connect the attributes of the given objects
        Args:
            driver: source of the connection
            driven: destiny of the connection
            attributes: attributes to connect p.e scale, translate
            axis: axis of the attribute p.e ['X', 'Y', 'Z'] or XYZ
        """
        for attribute in attributes:
            for axi in axis:
                driver.attr('%s%s' % (attribute, axi)).connect(driven.attr('%s%s' % (attribute, axi)))


    @staticmethod
    def treeTracker(start, nodeType, inputs=True, maxNodes=0):
        """
         Track since the start node all input graph or output graph, and return the
         desired nodetypes.
         :param start (str or pm):
         :param nodeType (str):
         :param inputs (bool): true inputs, false outputs
         :param maxNodes: maximum of found nodes, 0 equal to no maximum
        """
        if isinstance(start, str):
            start = pm.PyNode(start)
        output = []  # store here the results
        checkedNodes = set()

        def treeTracker_Recursive(start, nodeType):
            """
             recursive func to run over the graph
            """
            # track the plug, if not, it can give us erratic results
            if inputs:
                connectedPlugs = start.inputs(p=True)
            else:
                connectedPlugs = start.outputs(p=True)

            # transform all connectedInputs in connected nodes, and try to avoid duplicated nodes
            # with set() delete duplicated nodes from the list
            connectedNodes = set([plug.node() for plug in connectedPlugs])
            connectedNodes.difference_update(checkedNodes)
            checkedNodes.update(connectedNodes)

            # iterate over the found nodes
            for node in connectedNodes:
                if maxNodes == 0 or maxNodes > len(output):
                    # if the node is od the node type, save it
                    if node.type() == nodeType:
                        output.append(node)

                    if maxNodes != 0 and maxNodes <= len(output):
                        break
                    else:
                        # check the inputs or outputs of the node
                        treeTracker_Recursive(node, nodeType)

        # start recursive process
        treeTracker_Recursive(start, nodeType)

        return output


##############################
##Vector and math Operations##
##############################
def checkVectorType(vector):
    """
    Check vector type, tuple, list or pm
    :param vector:
    :return:
    """
    # check type # vector
    if isinstance(vector, list) or isinstance(vector, tuple):
        vector = pm.datatypes.Vector(vector[0], vector[1], vector[2])

    return pm.datatypes.Vector(vector[:3])


def checkMatrixType(matrix):
    """
    check matrix type, tuple, list or pm
    :param matrix:
    :return:
    """
    # matrix
    if isinstance(matrix, list) or isinstance(matrix, tuple):
        if len(matrix) == 16:
            matrix = pm.datatypes.Matrix([matrix[0], matrix[1], matrix[2], matrix[3]],
                                         [matrix[4], matrix[5], matrix[6], matrix[7]],
                                         [matrix[8], matrix[9], matrix[10], matrix[11]],
                                         [matrix[12], matrix[13], matrix[14], matrix[15]])
        if len(matrix) == 4:
            matrix = pm.datatypes.Matrix([matrix[0][0], matrix[0][1], matrix[0][2], matrix[0][3]],
                                         [matrix[1][0], matrix[1][1], matrix[1][2], matrix[1][3]],
                                         [matrix[2][0], matrix[2][1], matrix[2][2], matrix[2][3]],
                                         [matrix[3][0], matrix[3][1], matrix[3][2], matrix[3][3]])

    return matrix


class VectorMath_Nodes():
    """
    class based on common Node vector operations.
    This class exists for organize porpoises.
    """
    ## quaternions ##
    @staticmethod
    def quatToAxisAngle(quat):
        """
        Convert a quaternion attr in a angle and a vector
        :param quat (str or pm): plug attr with the quaternion
        :return([pm, pm]): [anglePlug, vectorPlug]
        """
        # check types
        if isinstance(quat, str):
            quat = pm.PyNode(quat)

        QTAA = pm.createNode("quatToAxisAngle")
        quat.connect(QTAA.inputQuat)

        return [QTAA.outputAngle, QTAA.outputAxis]


    @staticmethod
    def quatProd(quatA, quatB):
        """
        Multiply quaternions
        :param quatA: quat attribute
        :param quatB: quat attribute
        :return:
        """
        # check types
        values = [quatA, quatB]
        for i in range(len(values)):
            if isinstance(values[i], str):
                values[i] = pm.PyNode(values[i])

        # create node
        quatProd = pm.createNode("quatProd")
        values[0].connect(quatProd.input1Quat)
        values[1].connect(quatProd.input2Quat)

        return quatProd.outputQuat


    @staticmethod
    def quatInvert(quat):
        """
        Create a quatInverse node and return the quat output
        :param quat:
        :return:
        """
        # check type
        if isinstance(quat, str):
            quat = pm.PyNode(quat)

        quatInverse = pm.createNode("quatInvert")
        quat.connect(quatInverse.inputQuat)

        return quatInverse.outputQuat


    @staticmethod
    def quatSlerp(quatB, quatA, blend=0.5, angleInt=0):
        """
        create a quatSlerp node ans return the output attr
        blend 1 => full quatB
        :param quatA(str, pm, list): quat attr
        :param quatB(str, pm, list): quat attr
        :param blend(str, pm): blend weight
        :param angleInt(str, int): type interpolation: 0: shortest, 1: positive, 2: negative
        :return:
        """
        # check types
        values = [quatA, quatB, blend, angleInt]  # swap quatA and quatB
        for i in range(len(values)):
            if isinstance(values[i], str):
                values[i] = pm.PyNode(values[i])

        quatSlerp = pm.createNode("quatSlerp")
        # interpolation type
        if isinstance(values[3], pm.Attribute):
            values[3].connect(quatSlerp.angleInterpolation)
        else:
            quatSlerp.angleInterpolation.set(values[3])

        # blend
        if isinstance(values[2], pm.Attribute):
            values[2].connect(quatSlerp.inputT)
        else:
            quatSlerp.inputT.set(values[2])

        # quats
        for i in range(2):
            if isinstance(values[i], pm.Attribute):
                values[i].connect(quatSlerp.attr("input%sQuat" % (i+1)))
            else:
                quatSlerp.attr("input%sQuat" % (i + 1)).set(values[i])

        return quatSlerp.outputQuat


    @staticmethod
    def quatToEuler(input, rotateOrder=0):
        """
        Create a node to convert a quat to a euler rotate
        :param input(str, pm, list): quaternion attr or value
        :param rotateOrder(str, pm, int): attr to define rotation order
                                            0: xyz, 1: yzq, 2:zxy,
                                            3:xzy, 4:yxz, 5: zyx
        :return: outputRotate
        """
        # check types
        values = [input, rotateOrder]
        for i in range(len(values)):
            if isinstance(values[i], str):
                values[i] = pm.PyNode(values[i])

        # create node
        quatTEu = pm.createNode("quatToEuler")
        # rotate order
        if isinstance(values[1], pm.Attribute):
            values[1].connect(quatTEu.inputRotateOrder)
        else:
            quatTEu.inputRotateOrder.set(values[1])

        # connect quat
        if isinstance(values[0], pm.Attribute):
            values[0].connect(quatTEu.inputQuat)
        else:
            quatTEu.inputQuat.set(values[0])

        return quatTEu.outputRotate


    ## matrix ##
    @staticmethod
    def matrixDecompose(matrix):
        """
        Decompose a matrix into:
            0. quaternion.
            1. rotation.
            2. scale.
            3. shear.
            4. translate
        :param matrix (str or pm): attribute with the matrix
        :return: in order: quaternion, rotation, scale, shear, translate
        """
        # check types
        if isinstance(matrix, str):
            matrix = pm.PyNode(matrix)

        DM = pm.createNode("decomposeMatrix")
        matrix.connect(DM.inputMatrix)

        return DM.outputQuat, DM.outputRotate, DM.outputScale, DM.outputShear, DM.outputTranslate


    @staticmethod
    def matrix4by4(vectorX, vectorY, vectorZ, position=None):
        """
        Given the correct vectors, create a 4 by 4 matrix
        :param vectorX:
        :param vectorY:
        :param vectorZ:
        :param position:
        :return:
        """
        ## check types ##
        # get args and values
        argsStr = [VectorMath_Nodes.matrix4by4.func_code.co_varnames[i] for i in
                   range(VectorMath_Nodes.matrix4by4.func_code.co_argcount - 1)]

        argVal = [locals()[arg] for arg in argsStr]

        # prepare dictionaries
        # data types
        vectorList = {}
        for i, argStr in enumerate(argsStr):
            if isinstance(argVal[i], str):
                argVal[i] = pm.PyNode(argVal[i])
            if not (argVal[i].type() == 'double3' or argVal[i].type() == 'float3'):
                logger.info('%s must be type double3 or float3' % argVal[i])
                return
            # add to dictionary
            vectorList[argStr] = argVal[i]

        ## construct circuitry ##
        fourByfourMatrix = pm.createNode('fourByFourMatrix')
        # connect Vectors
        for i, argStr in enumerate(argsStr):
            childAttr = vectorList[argStr].children()

            for j, cAttr in enumerate(childAttr):
                cAttr.connect(fourByfourMatrix.attr('in%s%s' % (i, j)))

        # if position, connect too position
        if position:
            if isinstance(position, str):
                position = pm.PyNode(position)
            if not (position.type() == 'double3' or position.type() == 'float3'):
                logger.info('position must be type double3 or float3')
                return

            childAttr = position.children()
            for j, cAttr in enumerate(childAttr):
                cAttr.connect(fourByfourMatrix.attr('in3%s' % j))

        return fourByfourMatrix.output


    @staticmethod
    def matrixMult(*args):
        """
        return a plug with the result of multiply matrix
        :param args: matrix plugs
        :return:
        """
        multMatrixNode = pm.createNode('multMatrix')
        for i, matrix in enumerate(args):
            # check type
            if isinstance(matrix, str):
                matrix = pm.PyNode(matrix)
            # connect matrix
            matrix.connect(multMatrixNode.attr('matrixIn[%s]' % i))

        # return the resultant matrix
        return multMatrixNode.matrixSum


    @staticmethod
    def matrixInverse(matrix):
        """
        return a Plug with the inversed matrix
        :param matrix:
        :return:
        """
        # check types
        if isinstance(matrix, str):
            matrix = pm.PyNode(matrix)

        # create inverse matrix node
        inverseNode = pm.createNode('inverseMatrix')
        matrix.connect(inverseNode.inputMatrix)

        return inverseNode.outputMatrix


    ## vector ##
    @staticmethod
    def vectorProduct(vectorA, vectorB=None, operation=0, matrix=None, normalize=False):
        """
        Create a vector product node.
        it's useful for vector operations, and for extrat matrix vectors.
        :param vectorA:
        :param vectorB:
        :param operation (int): 0: no operation, 1: dot product, 2: cross product,
                                3: vector matrix product, 4: point matrix product.
        -vector Matrix Product (3) useful to extract rotation vectors from matrix.
        -point matrix product (4) useful to extract position vector from matrix.
        :param matrix:
        :param normalize:
        :return:
        # REVIEW: be careful with matrix attr connection, some times does not work
        """
        values = [vectorA, vectorB, matrix]
        for i in range(len(values)):
            if isinstance(values[i], str):
                values[i] = pm.PyNode(values[i])

        # create node
        vectorProduct = pm.createNode("vectorProduct")
        vectorProduct.normalizeOutput.set(normalize)
        vectorProduct.operation.set(operation)
        # matrix
        if matrix:
            values[2].connect(vectorProduct.matrix)

        # connect vectors
        for i in range(2):
            if isinstance(values[i], pm.Attribute):
                values[i].connect(vectorProduct.attr("input%s" % (i+1)))
            elif values[i] != None:
                vectorProduct.attr("input%s" % (i + 1)).set(values[i])

        return vectorProduct.output


    @staticmethod
    def dotProduct(vectorA, vectorB):
        """
        Create a conection based on a space deform to drive attributes
        :param driverVector(str or pm): output attr with vector info
        :param drivenVector(str or pm): output attr with vector info
        :param attributes(str): attributes that will be drived
        :return psDot: output product node with dot product
        """
        # check types
        if isinstance(vectorA, str):
            vectorA = pm.PyNode(vectorA)
        if isinstance(vectorB, str):
            vectorB = pm.PyNode(vectorB)

        # get ps dot
        dotProduct = pm.createNode('vectorProduct')
        dotProduct.operation.set(1)
        vectorA.connect(dotProduct.input1)  # connect driver vector
        vectorB.connect(dotProduct.input2)  # connect driven vector

        return dotProduct.output


    @staticmethod
    def crossProduct(vectorA, vectorB, normalized=False):
        """
        Create the circuitry necessary for colculate cross product between two vectors
        :param vectorA: output attr
        :param vectorB: output attr
        :param normalized: True or false
        :return: cross output attr
        """
        # check types
        if isinstance(vectorA, str):
            vectorA = pm.PyNode(vectorA)
        if isinstance(vectorB, str):
            vectorB = pm.PyNode(vectorB)

        crossProduct = pm.createNode('vectorProduct')
        crossProduct.operation.set(2)
        crossProduct.normalizeOutput.set(normalized)
        vectorA.connect(crossProduct.input1)
        vectorB.connect(crossProduct.input2)

        return crossProduct.output


    @staticmethod
    def projectVectorOntoPlane(vectorOutput, vectorNormal, normalized=False):
        """
        Calculate the vector projection onto a plane
        :param vectorOutput(str or pm): attribute with the vector
        :param vectorNormal(str or om): attribute with the vector
        :return:
        """
        # check types, must be attr type
        if isinstance(vectorOutput, str):
            vectorOutput = pm.PyNode(vectorOutput)
        if isinstance(vectorNormal, str):
            vectorNormal = pm.PyNode(vectorNormal)

        # normalize normal
        normalNormalize = pm.createNode('vectorProduct')
        normalNormalize.operation.set(0)  # no operation
        normalNormalize.normalizeOutput.set(1)  # normalize output
        vectorNormal.connect(normalNormalize.input1)

        ## get the projection of vectorOutput onto vectorNormal ##
        dotProduct = pm.createNode('vectorProduct')
        normalNormalize.normalizeOutput.set(0)  # NO normalize output
        dotProduct.operation.set(1)  # dot product
        vectorOutput.connect(dotProduct.input1)
        normalNormalize.output.connect(dotProduct.input2)

        # multiply normal by dot product
        normalMultiply = pm.createNode('multiplyDivide')
        normalMultiply.operation.set(1)  # multiply
        normalNormalize.output.connect(normalMultiply.input1)
        dotProduct.output.connect(normalMultiply.input2)

        # substract new vector from vector output
        substractVector = pm.createNode('plusMinusAverage')
        substractVector.operation.set(2)  # substract
        vectorOutput.connect(substractVector.input3D[0])
        normalMultiply.output.connect(substractVector.input3D[1])

        # if normalized, return the vector normalized
        if normalized:
            subsVecChann = substractVector.output3D.children()
            subsVecChannPlus = VectorMath_Nodes.plusMinusAverage(1, subsVecChann[0], subsVecChann[1], subsVecChann[2])

            logic1 = DGUtils.floatLogic(subsVecChannPlus, 0.001, 5)
            logic2 = DGUtils.floatLogic(subsVecChannPlus, -0.001, 4)
            addLogic=VectorMath_Nodes.plusMinusAverage(1, logic1, logic2)  # or condition

            nonZero = DGUtils.colorCondition(None, None, addLogic, substractVector.output3D,
                                             [0.001, 0.001, 0.001])
            normalizeVector = pm.createNode('vectorProduct')
            normalizeVector.operation.set(0)  # no operation
            normalizeVector.normalizeOutput.set(True)
            nonZero.connect(normalizeVector.input1)
            return normalizeVector.output

        return substractVector.output3D


    @staticmethod
    def getVectorBetweenTransforms(point1, point2, normalized=True):
        """
        Get the vector defined by two transform nodes. independent of the hierarchy
        the base of this method is set a vectorProduct node as dotMatrixProduct. and
        operate over a vector (0,0,0), this way we get the world space translation.
        :param point1: origin of the vector
        :param point2: end of the vector
        :param normalized: normalized or not
        :return:
        """
        # check data types
        if isinstance(point1, str):
            point1 = pm.PyNode(point1)
        if isinstance(point2, str):
            point2 = pm.PyNode(point2)

        # get point1 transform from transform node
        vector1Product = pm.createNode('vectorProduct')
        vector1Product.normalizeOutput.set(False)
        point1.worldMatrix[0].connect(vector1Product.matrix)
        # set vProduct node
        vector1Product.operation.set(4)
        for axis in 'XYZ':
            vector1Product.attr('input1%s' % axis).set(0)

        #get point2 Transform Node
        vector2Product = pm.createNode('vectorProduct')
        vector2Product.normalizeOutput.set(False)
        point2.worldMatrix[0].connect(vector2Product.matrix)
        # set v2Product node
        vector2Product.operation.set(4)
        for axis in 'XYZ':
            vector2Product.attr('input1%s' % axis).set(0)

        # substract vector1 from vector2
        plusMinus=pm.createNode('plusMinusAverage')
        plusMinus.operation.set(2) # substract
        vector1Product.output.connect(plusMinus.input3D[1])  # vector2 - vector1
        vector2Product.output.connect(plusMinus.input3D[0])

        # finally connect to to another vector product and normalize if arg normalize is true
        vectorBetween = pm.createNode('vectorProduct')
        vectorBetween.operation.set(0)  # no operation
        vectorBetween.normalizeOutput.set(normalized)
        plusMinus.output3D.connect(vectorBetween.input1)

        return vectorBetween, vector1Product, vector2Product


    ## aritmethic ##
    @staticmethod
    def absVal(value):
        """
        Return a plug with the abs value
        :param value: plug
        :return:
        """
        # check node types
        if isinstance(value, str):
            value = pm.PyNode(value)

        # square power
        powerNode = pm.createNode('multiplyDivide')
        powerNode.operation.set(3)  #power
        for axis in 'XYZ':
            powerNode.attr('input2%s' % axis).set(2)

        value.connect(powerNode.input1X)

        # square root
        squareNode = pm.createNode('multiplyDivide')
        squareNode.operation.set(3)  # power
        for axis in 'XYZ':
            squareNode.attr('input2%s' % axis).set(.5)
        powerNode.outputX.connect(squareNode.input1X)

        return squareNode.outputX


    @staticmethod
    def plusMinusAverage(operation=1, *args):
        """
        create a plusminusaverage node with the input *args
        :param operation:
        :param values:
        :return:
        """
        # check types
        values = list(args)
        for i in range(len(values)):
            if isinstance(values[i], str):
                values[i] = pm.PyNode(values[i])
                print values[i], type(values[i])

        # create node
        plusMinus = pm.createNode("plusMinusAverage")
        plusMinus.operation.set(operation)

        if isinstance(values[0], float) or isinstance(values[0], int):
            attrDim = "input1D"
        elif isinstance(values[0], list):
            attrDim = "input1D"
        elif isinstance(values[0], pm.Attribute):
            attrDim = "input3D" if values[0].type() == "double3" or values[0].type() == "float3" else "input1D"

        for i in range(len(values)):
            if isinstance(values[i], float) or isinstance(values[i], int):
                plusMinus.attr(attrDim+"[%s]" % i).set(values[i])
            elif isinstance(values[i], pm.Attribute):
                values[i].connect(plusMinus.attr(attrDim + "[%s]" % i))

        return plusMinus.attr(attrDim.replace("input", "output"))


    @staticmethod
    def multiplyDivive(valueA, valueB, operation=1):

        # check types
        values = [valueA, valueB]
        for i in range(len(values)):
            if isinstance(values[i], str):
                values[i] = pm.PyNode(values[i])

            elif isinstance(values[i], list):
                # if is a list, look for posible attributes inside
                for j in range(3):
                    if isinstance(values[i][j], str):
                        values[i][j] = pm.PyNode(values[i][j])

        axis = "XYZ"
        multiplyDivide = pm.createNode("multiplyDivide")
        multiplyDivide.operation.set(operation)
        for i in range(len(values)):
            if isinstance(values[i], pm.Attribute):
                if values[i].type() == "double3" or values[i].type() == "float3":
                    values[i].connect(multiplyDivide.attr("input%s" % str(i+1)))
                else:
                    values[i].connect(multiplyDivide.attr("input%sX" % str(i+1)))

            else:
                if isinstance(values[i], list):
                    for j, ax in enumerate(axis):
                        if isinstance(values[i][j], pm.Attribute):
                            values[i][j].connect(multiplyDivide.attr("input%s%s" % (str(i+1), ax)))
                        elif values[i][j] != None:
                            multiplyDivide.attr("input%s%s" % (str(i + 1), ax)).set(values[i][j])

                else:
                    multiplyDivide.attr("input%s" % str(i + 1)).set(values[i])

        return multiplyDivide.output


    @staticmethod
    def multDoubleLinear(valueA, valueB):
        """
        Create a multDoubleLinear node and return the output.
        the difference with multiplyDivide is that double linear works only for single attributes.
        and there aren't operation attribute
        :param valueA(str or pm or float): first value
        :param valueB(str or pm or float): second value
        :return:
        """
        # check types
        values = [valueA, valueB]
        for i in range(len(values)):
            if isinstance(values[i], str):
                values[i] = pm.PyNode(values[i])

        # create Node
        multDoubleLinear = pm.createNode("multDoubleLinear")
        for i in range(len(values)):
            if isinstance(values[i], pm.Attribute):
                values[i].connect(multDoubleLinear.attr("input%s" % (i+1)))
            else:
                multDoubleLinear.attr("input%s" % (i+1)).set(values[i])

        return multDoubleLinear.output


class VectorMath():
    """
    class based on common vector operations.
    This class exists for organize porpoises.
    No nodes operations
    """

    @staticmethod
    def barycentricCoords(vectorU, vectorV, vectorBar):
        """
        given two vectors, return the u,v barycentric coords of the vectorBar
        :param vectorA (mVector):
        :param vectorB (mVector):
        :param point (mPoint):
        :return:
        """
        if not isinstance(vectorU, OpenMaya.MVector):
            vectorU = OpenMaya.MVector(vectorU)

        if not isinstance(vectorV, OpenMaya.MVector):
            vectorV = OpenMaya.MVector(vectorV)

        if not isinstance(vectorBar, OpenMaya.MVector):
            vectorBar = OpenMaya.MVector(vectorBar)

        # denominator
        denom = ((vectorU * vectorU) * (vectorV * vectorV) - (vectorU * vectorV) * (vectorV * vectorU))
        # u and V
        u = ((vectorV * vectorV) * (vectorBar * vectorU) - (vectorV * vectorU) * (vectorBar * vectorV)) / denom
        v = ((vectorU * vectorU) * (vectorBar * vectorV) - (vectorU * vectorV) * (vectorBar * vectorU)) / denom

        return u, v


    @staticmethod
    def orientMatrixToPlane(matrix, plane=None):
        """
        Deprecated, use orientMatrixToVector
        Conserve the general orient of a matrixTransform, but aligned to a plane.
        option to select the respect axis
        Args:
            controller(pm.transform): transform matrix
            plane(string): zx, xy, yz  lower case, first vector is the prefered vector
        """
        if not plane:
            logger.info('no plane')
            return matrix
        elif len(plane) > 2:
            logger.info('insert a valid plane')
            return matrix

        # check matrix type
        matrix = checkMatrixType(matrix)

        axisList = 'xyz'

        vectors = {}
        vIndex = 0
        # store initial vectors
        for axis in axisList:
            vectors[axis] = OpenMaya.MVector(matrix[vIndex][0],matrix[vIndex][1],matrix[vIndex][2])
            vIndex += 1

        # compare dot products, and find the nearest vector to plane vector
        planeVector = [0 if axis in plane else 1 for axis in axisList]  # plane vector (1,0,0) or (0,1,0) or (0,0,1)
        planeVector = OpenMaya.MVector(planeVector[0], planeVector[1], planeVector[2])
        dotValue = None
        respectVector = None
        for axis in axisList:
            newDot = abs(planeVector * vectors[axis])
            if dotValue < newDot:
                dotValue = newDot
                respectVector = axis

        # find resettable axis
        resetAxis = axisList  # convert axis list in axis string
        for axis in plane:
            resetAxis = resetAxis.replace(axis, '')

        # reset the axis
        resetPlane = ''
        for key, vector in vectors.iteritems():
            if key == respectVector:  # this is not necessary to reset
                continue
            setattr(vector, resetAxis, 0)
            vector.normalize()
            resetPlane += key  # edited vectors, projected over the plane

        # reconstruct matrix
        # use comapreVectors to avoid negative scales, comparing dot product
        compareVector = OpenMaya.MVector(vectors[respectVector])
        vectors[respectVector] = vectors[resetPlane[0]] ^ vectors[resetPlane[1]]
        if vectors[respectVector] * compareVector < 0:  # if dot negative, it will get as result a negative scale
            vectors[respectVector] = vectors[resetPlane[1]] ^ vectors[resetPlane[0]]
        vectors[respectVector].normalize()  # normalize
        compareVector = OpenMaya.MVector(vectors[resetPlane[1]])
        vectors[resetPlane[1]] = vectors[respectVector] ^ vectors[resetPlane[0]]
        if compareVector * vectors[resetPlane[1]] < 0:
            vectors[resetPlane[1]] = vectors[resetPlane[0]] ^ vectors[respectVector]
        vectors[resetPlane[1]].normalize()  # normalize

        returnMatrix = pm.datatypes.Matrix(
             [vectors[axisList[0]].x, vectors[axisList[0]].y, vectors[axisList[0]].z, matrix[0][3]],
             [vectors[axisList[1]].x, vectors[axisList[1]].y, vectors[axisList[1]].z, matrix[1][3]],
             [vectors[axisList[2]].x, vectors[axisList[2]].y, vectors[axisList[2]].z, matrix[2][3]],
             [matrix[3][0], matrix[3][1], matrix[3][2], matrix[3][3]])

        return returnMatrix


    @staticmethod
    def orientMatrixToVector(matrix, vector, matrixAxis=None):
        """
        orient the nearest axis of the matrix to the vector
        :param matrix:
        :param vector:
        :param matrixAxis: align the desired matrix axis. "x", "y", "z"
        :return:
        """
        # check types
        matrix = checkMatrixType(matrix)
        vector = checkVectorType(vector)
        vector.normalize()

        # find nearest axis to vector
        # compare dot products, and find the nearest vector to plane vector
        dotValue = 0
        nrtAId = None
        MVectr = []

        for i in range(3):
            MVectr.append(pm.datatypes.Vector(matrix[i][:3]))
            newDot = MVectr[-1] * vector
            if abs(dotValue) < abs(newDot):
                dotValue = newDot
                nrtAId = i

        if matrixAxis:
            # override if there is a specific matrix Axis
            axis = "xyz"
            nrtAId = axis.index(matrixAxis)
            dotValue = MVectr[nrtAId] * vector

        newMatrixVec = []
        for i in range(3):
            if i == nrtAId:
                newMatrixVec.append(vector * dotValue / abs(dotValue))
                continue

            newMatrixVec.append(VectorMath.projectVectorOntoPlane(MVectr[i], vector))

        # cross products to assure ortonormal matrix
        for i in range(3):
            newMatrixVec[(i+nrtAId+1)%3] = (newMatrixVec[(i+nrtAId+2)%3] ^ newMatrixVec[(i+nrtAId)%3])
            newMatrixVec[(i+nrtAId+1)%3].normalize()

        return pm.datatypes.Matrix([newMatrixVec[0].x, newMatrixVec[0].y, newMatrixVec[0].z, 0],
                                   [newMatrixVec[1].x, newMatrixVec[1].y, newMatrixVec[1].z, 0],
                                   [newMatrixVec[2].x, newMatrixVec[2].y, newMatrixVec[2].z, 0],
                                   matrix[3])


    @staticmethod
    def projectVectorOntoPlane(vector, normal):
        """
        Calculate the vector projection onto a plane
        :param vectorOutput(str or pm): attribute with the vector
        :param vectorNormal(str or om): attribute with the vector
        :return:
        """
        # check types, must be attr type
        vector = checkVectorType(vector)
        normal = checkVectorType(normal)

        normal.normalize()

        # proj vector onto normal
        projVec = VectorMath.projectVector(vector, normal)

        print "Vectors"
        print type(vector - projVec)

        return pm.datatypes.Vector(vector - projVec)


    @staticmethod
    def reflectedMatrix(matrix, flip=False, refMatrix=pm.datatypes.Matrix([-1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1])):
        """
        Return a reflected matrix. If flip is false, with no degative scales
        :param matrix:
        :param refMatrix:
        :return:
        """
        # check types
        matrix = checkMatrixType(matrix)
        refMatrix = checkMatrixType(refMatrix)

        matrixDet = matrix.det()
        # new matrix, remember the order is important
        returnMatrix = matrix * refMatrix

        # compare determinants, this way avoid undesired flipped axis
        if not flip:
            for i in range(3):
                if matrixDet != returnMatrix.det():
                    returnMatrix[i] *= -1
                else:
                    break

        return returnMatrix


    @ staticmethod
    def reflectedVectorByMatrix(vector, matrix=pm.datatypes.Matrix([-1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1])):
        """
        Return a Vector reflected by a reflection matrix
        default mirro x axis
        :param vector:
        :param matrix:
        :return:
        """
        # check data type
        # vector
        vector = checkVectorType(vector)
        matrix = checkMatrixType(matrix)

        return matrix * vector



    @staticmethod
    def reflectedVector(vector, normal):
        """
        Return the vector reflected over another vector (normal)
        :param vector:
        :param normal:
        :return:
        """
        pass
        # check data type



    @staticmethod
    def projectVector(vector, normal):
        """
        Return the vector projected over another vector (normal)
        :param vector:
        :param normal:
        :return:
        """
        # check types, change to pm vectors
        # vector
        vector = checkVectorType(vector)
        # normal
        normal = checkVectorType(normal)

        projection = (vector*normal/(normal.length() ** 2.0)) * normal
        return pm.datatypes.Vector(projection)


#############
## SYSTEMS ##
#############
# classes to automatize rig systems
class _System(object):
    """
    Base abstract class for all systems
    """
    def __init__(self, baseName):
        # here must be added the controllers
        # controllers must be empty transform nodes
        self.controllers = []
        self.baseName = baseName
        self.systemGrp = '%s_grp' % self.baseName  # parent of the system
        self.noXformGrp = '%s_noXform_grp' % self.baseName  # parent of noxform objects
        self.controllerGrp = '%s_controllers_grp' % self.baseName  # parent of controllers

    def buildSystem(self):
        """
        this method must be override.
        here must be the system construction.
        :return:
        """
        pass

    def createControllers(self, ctrType='pole', scale=1):
        """
        Add shapes to the controllers.
        Controllers should be empty transforms nodes
        TODO: Option to add custom controllers
        :return:
        """
        if not self.controllers:
            logger.info('Call buildSystem first')
            return

        if type(ctrType) == str:
            ctrShapesTrns = createController('tempCtr', ctrType, 'general', getCurrentPath(), scale)
            ctrShapes = ctrShapesTrns.getShapes()

        elif type(ctrType) == pm.nodetypes.Transform:
            ctrShapesTrns = ctrType
            ctrShapes = ctrType.getShapes()

        for controller in self.controllers:
            for ctrShape in ctrShapes:
                controller.addChild(ctrShape, add=True, s=True)

        # delete transform node of the controller
        pm.delete(ctrShapesTrns)

    def createControllersGrp(self):
        self.controllerGrp = pm.group(empty=True, name=self.controllerGrp)

    def createSystemGrp(self):
        """
        must be called at the end
        :return:
        """
        self.systemGrp = pm.group(empty=True, name=self.systemGrp)
        # try parent ctr grp
        try:
            self.systemGrp.addChild(self.controllerGrp)
        except:
            pass
        # try parent noXform grp
        try:
            self.systemGrp.addChild(self.noXformGrp)
        except:
            pass

    def createNoXformGrp(self):
        self.noXformGrp = pm.group(empty=True, name=self.noXformGrp)
        self.noXformGrp.inheritsTransform.set(False)  # don't affect parents transforms


class nurbsStripPointController(_System):
    """
    Create simple controllers for a nurb surface strip
    """
    def __init__(self, nurbsStrip, baseName='nurbsPointController'):
        # check dataType
        if isinstance(nurbsStrip, str):
            nurbsStrip = pm.PyNode(nurbsStrip)
        if isinstance(nurbsStrip, pm.nodetypes.Transform):
            nurbsStrip = nurbsStrip.getShape()

        self.nurbsStrip = nurbsStrip

        # base init
        super(nurbsStripPointController, self).__init__(baseName)

    def buildSystem(self):
        # get CV points
        nurbsStripTransforms = transformDriveNurbObjectCV(self.nurbsStrip)

        self.createControllersGrp()

        # create first level controllers
        firstLvlCtr = []
        for i in range(0, len(nurbsStripTransforms),2):
            ctr1 = pm.group(empty=True, name='%s_ctr%s1_ctr' % (self.baseName, i/2))
            ctr2 = pm.group(empty=True, name='%s_ctr%s2_ctr' % (self.baseName, i/2))

            # create general ctr
            generalCtr = pm.group(empty=True, name='%s_ctr%s3_ctr' % (self.baseName, i / 2))
            # pos general ctr
            pm.xform(generalCtr, ws=True, m=pm.xform(nurbsStripTransforms[i], ws=True, q=True, m=True))
            generalCtr.setTranslation((nurbsStripTransforms[i].getTranslation() + nurbsStripTransforms[i+1].getTranslation()) / 2)
            self.controllers.append(generalCtr)
            # child ctrGrp
            self.controllerGrp.addChild(generalCtr)

            # copy transforms and parent ctr
            for j, ctr in enumerate([ctr1,ctr2]):
                pm.xform(ctr, ws=True, m=pm.xform(nurbsStripTransforms[i+j], ws=True, q=True, m=True))
                ctr.addChild(nurbsStripTransforms[i+j])
                generalCtr.addChild(ctr)
                # append to ctr list
                self.controllers.append(ctr)

        # create roots
        createRoots(self.controllers)


class VariableFk(_System):
    """
    Create a variableFk system
    :param curve:
    :param numJoints:
    :return:
    """
    def __init__(self, jointList, curve=None, numControllers=3, baseName='variableFk'):
        if not curve:
            curve = createCurveFromTransforms(jointList, 3)[1]
        else:
            # check data type
            if isinstance(curve, str):
                curve = pm.PyNode(curve)
            if isinstance(curve, pm.nodetypes.Transform):
                curve = curve.getShape()

        # call base __init__
        super(VariableFk, self).__init__(baseName)

        # arg attr
        self.curve = curve
        self.jointList = jointList
        self.numControllers = numControllers

        # container of the controllers and surface
        self.createNoXformGrp()

        # container for the system, joints
        self.createControllersGrp()


    def buildSystem(self):
        """
        Build System
        :return:
        """
        numJoints = len(self.jointList)

        ## duplicate joints ##
        jointsSkin = [joint.duplicate(po=True)[0] for joint in self.jointList]
        for i in range(len(jointsSkin) - 1):
            jointsSkin[i].addChild(jointsSkin[i + 1])
        self.controllerGrp.addChild(jointsSkin[0])

        # create system controller
        mainCtr = squareController(8, 8, 'x', 4)
        self.controllerGrp.addChild(mainCtr)  # add controller to ctrGrp
        pm.xform(mainCtr, ws=True, m=pm.xform(jointsSkin[0], q=True, ws=True, m=True))
        mainCtr.addChild(jointsSkin[0])  # add jointSkin chain

        # joint skin roots, for conserve direction
        jointsSkinRoots = createRoots(jointsSkin)
        # root of main ctr
        mainCtrRoot = createRoots([mainCtr])

        # create nurbs surface from curve
        surface = curveToSurface(self.curve, 2.5, numJoints)
        surfaceShape = surface.getShape()

        self.noXformGrp.addChild(surface)

        # connect joints and surface by skinCluster
        skinCluster = pm.skinCluster(jointsSkin, surfaceShape, mi=1)

        ## create controllers ##
        self.controllerList = []
        jointsRoots = []
        for i in range(self.numControllers):
            # normal x axis
            #controller = squareController(5.0, 5.0, 'x', 13)
            controller = pm.group(empty=True, name='%s_%s_ctr' % (self.baseName, i+1))
            # copy rotation from joint
            pm.xform(controller, ws=True, m=pm.xform(jointsSkin[0], q=True, ws=True, m=True))
            # create fallof attr
            pm.addAttr(controller, ln='fallof', sn='fallof', minValue=0.01, type='float',
                       defaultValue=0.2, maxValue=1.0, k=True)

            # create a root on each joint for controller, each controller will be connected on one root
            jointsRoots.append(createRoots(jointsSkin, '_auto'))

            self.controllerList.append(controller)
            self.noXformGrp.addChild(controller)

        # root controllers
        controllerRoots = createRoots(self.controllerList)

        ## snap root to surface ##
        for i, root in enumerate(controllerRoots):
            pointOnSurf = pm.createNode('pointOnSurfaceInfo')
            vValue = surfaceShape.maxValueV.get() / 2
            pointOnSurf.parameterV.set(vValue)
            surfaceShape.worldSpace[0].connect(pointOnSurf.inputSurface)

            # construct two transform matrix with fourByFourMatrix
            matrixNurbs = pm.createNode('fourByFourMatrix')
            matrixNurbIni = pm.createNode('fourByFourMatrix')  # with this we calculate the offset
            for n, attr in enumerate(['normalizedTangentU', 'normalizedNormal', 'normalizedTangentV', 'position']):
                for j, axis in enumerate('XYZ'):
                    pointOnSurf.attr('%s%s' % (attr, axis)).connect(matrixNurbs.attr('in%s%s' % (n, j)))
                    if n < 3:
                        # store matrix info
                        matrixNurbIni.attr('in%s%s' % (n, j)).set(pointOnSurf.attr('%s%s' % (attr, axis)).get())

            # store initial root matrix
            rootMatrix = pm.xform(root, ws=True, q=True, m=True)
            rootMatrixNode = pm.createNode('fourByFourMatrix')
            for n, val in enumerate(rootMatrix):
                rowPos = n % 4
                colPos = n // 4
                if colPos == 3 and rowPos < 3:
                    val = 0
                elif colPos == 3 and rowPos == 3:
                    val = 1
                else:
                    val = val
                rootMatrixNode.attr('in%s%s' % (colPos, rowPos)).set(val)

            # calcOffset
            inverseNode = pm.createNode('inverseMatrix')
            rootMatrixNode.output.connect(inverseNode.inputMatrix)
            offsetNode = pm.createNode('multMatrix')
            matrixNurbIni.output.connect(offsetNode.matrixIn[0])
            inverseNode.outputMatrix.connect(offsetNode.matrixIn[1])

            # use mult matrix to add the offset
            multMatrix = pm.createNode('multMatrix')
            offsetNode.matrixSum.connect(multMatrix.matrixIn[0])
            matrixNurbs.output.connect(multMatrix.matrixIn[1])

            # now we need to read the matrix
            decompose = pm.createNode('decomposeMatrix')
            multMatrix.matrixSum.connect(decompose.inputMatrix)
            # and connect to the root controller
            decompose.outputTranslate.connect(root.translate)
            decompose.outputRotate.connect(root.rotate)

            # add slide attr to controller
            defaultSlide = (i + 1) / (float(self.numControllers + 1))
            pm.addAttr(self.controllerList[i], ln='slide', sn='slide', minValue=0.0, type='float', defaultValue=defaultSlide,
                       maxValue=1.0, k=True)
            # connect to Uparamenter
            self.controllerList[i].slide.connect(pointOnSurf.parameterU)

        # TODO add system general control
        # connect variableFk formula
        for i, rootChain in enumerate(jointsRoots):
            controller = self.controllerList[i]
            controllerRoot = controllerRoots[i]

            # total joints affected
            totalJointsA = pm.createNode('multiplyDivide')
            totalJointsA.operation.set(1)  # multiply
            totalJointsA.input1X.set(numJoints / 2)  # double
            controller.fallof.connect(totalJointsA.input2X)

            for j, rootJoint in enumerate(rootChain):
                # calculate the joint point
                jointPoint = j / (numJoints - 1.0)  # range 0<->1 review
                rootJoint.rename('%s_jointOffset' % controllerRoot)

                # distance from controller
                distanceCtr = pm.createNode('plusMinusAverage')
                distanceCtr.operation.set(2)  # substract
                distanceCtr.input1D[0].set(jointPoint)
                controller.slide.connect(distanceCtr.input1D[1])
                ## absoluteVal ##
                square = pm.createNode('multiplyDivide')
                square.operation.set(3)  # power
                square.input2X.set(2)  # square
                distanceCtr.output1D.connect(square.input1X)
                # squareRoot
                squareRoot = pm.createNode('multiplyDivide')
                squareRoot.operation.set(3)  # power
                squareRoot.input2X.set(.5)  # square
                square.outputX.connect(squareRoot.input1X)

                ## compare with fallof ## ((f-(|p-c|))/f)
                fallofDst = pm.createNode('plusMinusAverage')
                fallofDst.operation.set(2)  # subtract
                controller.fallof.connect(fallofDst.input1D[0])
                squareRoot.outputX.connect(fallofDst.input1D[1])
                # if the result < 0, stay in 0
                condition = pm.createNode('condition')
                condition.operation.set(2)  # greater than
                condition.secondTerm.set(0)
                condition.colorIfFalseR.set(0)
                fallofDst.output1D.connect(condition.firstTerm)
                fallofDst.output1D.connect(condition.colorIfTrueR)

                ## normalize the resutlt ##
                rotationMult = pm.createNode('multiplyDivide')
                rotationMult.operation.set(2)  # divide
                condition.outColorR.connect(rotationMult.input1X)
                controller.fallof.connect(rotationMult.input2X)

                # divide normalized value
                distRotation = pm.createNode('multiplyDivide')
                distRotation.operation.set(2)  # divide
                rotationMult.outputX.connect(distRotation.input1X)
                totalJointsA.outputX.connect(distRotation.input2X)

                ## connect to root joint and controller rotation ##
                rotationRoot = pm.createNode('multiplyDivide')
                rotationRoot.operation.set(1)  # multiply
                # multiply with controller
                controller.rotate.connect(rotationRoot.input1)
                for axis in 'XYZ':
                    distRotation.outputX.connect(rotationRoot.attr('input2%s' % axis))
                # connect to root
                rotationRoot.output.connect(rootJoint.rotate)

        # lock and hide attributes
        lockAndHideAttr(self.controllerList, True, False, True)

        # connect joints
        for i, joint in enumerate(self.jointList):
            pm.orientConstraint(jointsSkin[i], joint, maintainOffset=False)
            pm.pointConstraint(jointsSkin[i], joint, maintainOffset=False)


class WireCurve(_System):
    """
    Build a wire system on a curve, trying to maintain the length of the curve when move extremes.
    :param curve(str or pm):
    :return:
    TODO: scalable
    TODO: review formula, when vector length is minor than ini value, it grows to much
    """
    def __init__(self, curve, baseName='wireSystem'):
        """
        Constructor
        :param curve:
        :param baseName: base name of the system
        """

        self.curve = curve
        # check type
        if isinstance(self.curve, str):
            self.curve = pm.PyNode(self.curve)
        if isinstance(self.curve, pm.nodetypes.Transform):
            self.curve = self.curve.getShape()

        # call base __init__
        super(VariableFk, self).__init__(baseName)


    def buildSystem(self):
        """
        Construct the system
        :return:
        """
        # rebuild the curve, d=3 minimum 5 cv's.
        # curve = curveTransform.duplicate(name=('%s_dup_curve') % baseName)[0]
        pm.rebuildCurve(self.curve, ch=False, rpo=True, rt=False, end=True, kr=False, kep=True,
                        kt=False, s=self.curve.numCVs(), d=3, tol=0.01)

        # get curve points and connect a transform
        self.curvePoints = transformDriveNurbObjectCV(self.curve)

        curveLength = self.curve.length()

        # create no transform group
        self.createNoXformGrp()
        pm.parent(self.curvePoints, self.noXformGrp)  # addChild are given error with lists
        self.noXformGrp.addChild(self.curve.getTransform())

        # create to controllers, one for extreme of the curve
        self.controllers = []
        for i in range(2):
            ctr = pm.group(empty=True, name= '%s_%s_ctr' % (self.baseName, i + 1))
            pointId = -1 if i % 2 else 0  # check if is ini or final
            nextPointId = -1 if i % 2 else 1
            pm.xform(ctr, ws=True, m=pm.xform(self.curvePoints[pointId], ws=True, q=True, m=True))
            self.controllers.append(ctr)
            # parent curve points
            ctr.addChild(self.curvePoints[pointId])
            ctr.addChild(self.curvePoints[pointId + nextPointId])

        ## Vector controller node system ##
        # base Node system, vector between child points of the controllers
        # get transform worldSpace, point1
        # vectorProduct1 must be added later
        vectorBetCtr, vectorProduct1, vectorProduct2 = VectorMath_Nodes.getVectorBetweenTransforms(self.curvePoints[1], self.curvePoints[-2],
                                                                                                   False)

        # distance between points, useful later
        distanceBetween = pm.createNode('distanceBetween')
        self.curvePoints[1].worldMatrix[0].connect(distanceBetween.inMatrix1)
        self.curvePoints[-2].worldMatrix[0].connect(distanceBetween.inMatrix2)

        # cut the vector in sections, one per controller minus 1
        cutVector = pm.createNode('multiplyDivide')
        cutVector.operation.set(2)  # divide
        for axis in 'XYZ':
            cutVector.attr('input2%s' % axis).set(len(self.curvePoints) - 1)  # set the divide value
        vectorBetCtr.output.connect(cutVector.input1)

        # multiplicator factor by distance, this is to make the points nearest to the line between controllers
        # depending on distance
        # offsetVector multiply formula: 1-((l-lini)/(L-lini)) min:0
        substractDist = pm.createNode('plusMinusAverage')
        substractDist.operation.set(2)  # subtract
        distanceBetween.distance.connect(substractDist.input1D[0])
        substractDist.input1D[1].set(distanceBetween.distance.get())

        # Divide by curve length minus initial length
        curveLengthDivide = pm.createNode('multiplyDivide')
        curveLengthDivide.operation.set(2)  # divide
        substractDist.output1D.connect(curveLengthDivide.input1X)
        curveLengthDivide.input2X.set(curveLength - distanceBetween.distance.get())

        # invert: 1 - curveLengthDivide
        invertValue = pm.createNode('plusMinusAverage')
        invertValue.operation.set(2)  # substract
        invertValue.input1D[0].set(1)
        curveLengthDivide.outputX.connect(invertValue.input1D[1])
        # condition, 0 is the min value
        condition = pm.createNode('condition')  # multiply this by the vector
        condition.operation.set(3)  # greater or equal
        condition.colorIfFalse.set(pm.datatypes.Point(0, 0, 0))
        condition.secondTerm.set(0)
        invertValue.output1D.connect(condition.firstTerm)
        invertValue.output1D.connect(condition.colorIfTrueR)

        ## per CV node system ##
        for i, point in enumerate(self.curvePoints[2:-2]):
            multiplyVector = pm.createNode('multiplyDivide')
            multiplyVector.operation.set(1)  # multiply
            for axis in 'XYZ':
                multiplyVector.attr('input2%s' % axis).set(i + 2)
            cutVector.output.connect(multiplyVector.input1)

            # add the first controller position
            addPos1 = pm.createNode('plusMinusAverage')
            multiplyVector.output.connect(addPos1.input3D[0])
            vectorProduct1.output.connect(addPos1.input3D[1])

            # multiply offset vector by multiplicator factor
            # this way we transform the wire in a line depending on the distance
            vectorMultipler = pm.createNode('multiplyDivide')
            vectorMultipler.input1.set(point.translate.get() - pm.datatypes.Point(addPos1.output3D.get()))
            for axis in 'XYZ':
                condition.outColorR.connect(vectorMultipler.attr('input2%s' % axis))

            # pose final cv
            posVector = pm.createNode('plusMinusAverage')
            # vector between CV point and between controllers point
            vectorMultipler.output.connect(posVector.input3D[0])
            addPos1.output3D.connect(posVector.input3D[1])

            # connect to point
            posVector.output3D.connect(point.translate)