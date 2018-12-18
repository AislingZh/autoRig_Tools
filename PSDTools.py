from maya import cmds
import pymel.core as pm
from maya import OpenMaya
import math


def extractPosesPoseEditor():
    poseSelection = pm.ls(sl=True)
    for poseSel in poseSelection:
        poses = pm.poseInterpolator(poseSel, q=True, poseNames=True)

        # get Blendshape node
        poseSelShape = poseSel.getShape()
        blendShapeNode = poseSelShape.output.outputs()[0]

        mesh = pm.PyNode(blendShapeNode.getGeometry()[0])
        meshTransform = mesh.getTransform()

        for pose in poses:
            if pose == 'neutral' or pose == 'neutralSwing' or pose == 'neutralTwist':
                continue

            pm.poseInterpolator(poseSel, edit=True, goToPose=pose)

            # duplicate geo
            meshDup = meshTransform.duplicate()[0]
            meshDup.setParent(w=True)
            meshDup.rename(pose + '_mesh')

        pm.poseInterpolator(poseSel, edit=True, goToPose='neutral')


def deltaCorrective(joints, bShape):
    """
    extract and apply delto to a blendShape
    """

    mesh = pm.PyNode(bShape.getGeometry()[0])
    meshTransform = mesh.getTransform()

    for joint in joints:
        # create poseInterpolator
        poseInterpolator = pm.PyNode(pm.poseInterpolator(joint, name=str(joint) + '_poseInterpolator')[0])
        poseInterpolatorShape = poseInterpolator.getShape()
        print poseInterpolator

        # create basic poses
        for i, pose in enumerate(['neutral', 'neutralSwing', 'neutralTwist']):
            pm.poseInterpolator(poseInterpolator, e=True, addPose=pose)
            poseInterpolatorShape.pose[i].poseType.set(i)

        for rot in ([0, 90, 0], [0, -90, 0], [0, 0, 90], [0, 0, -90]):
            baseMesh = meshTransform.duplicate(name=str(joint) + ('_baseMesh'))[0]
            baseMesh.setParent(w=True)

            joint.setRotation(rot, 'object')
            negativeMesh = meshTransform.duplicate(name=str(joint) + ('_negative'))[0]
            negativeMesh.setParent(w=True)
            joint.setRotation([0, 0, 0], 'object')

            deltaMush = cmds.deltaMush(str(meshTransform), si=180, ss=0.1)
            cmds.dgeval(deltaMush)
            # set poses
            joint.setRotation(rot, 'object')
            namePose = str(joint) + ('_%s_%s_%s' % (rot[0], rot[1], rot[2])).replace('-', 'n')
            pm.poseInterpolator(poseInterpolator, e=True, addPose=namePose)

            # duplicate mesh
            positive = meshTransform.duplicate(name=namePose)[0]
            positive.setParent(w=True)

            # get delta
            deltaShape = getDelta(positive.getShape(), negativeMesh.getShape(), baseMesh.getShape())

            pm.delete(baseMesh)
            cmds.delete(deltaMush)

            # create bShape
            weightIndex = bShape.numWeights()
            bShape.addTarget(mesh, weightIndex, deltaShape, 1.0)

            joint.setRotation([0, 0, 0], 'object')


def getDelta(positive, negative, base):
    """
    space matrix
    """
    diferenceIndex = []
    for i, point in enumerate(positive.getPoints('object')):
        if point != negative.getPoint(i, 'object'):
            diferenceIndex.append(i)

    # duplicate base mesh
    baseDup = base.duplicate()[0].getShape()

    util = OpenMaya.MScriptUtil()

    sel = OpenMaya.MSelectionList()
    for i in (negative, base):
        sel.add(str(i))

    # negative
    mObject = OpenMaya.MObject()
    sel.getDependNode(0, mObject)
    negativeMFN = OpenMaya.MFnMesh(mObject)
    negativeIt = OpenMaya.MItMeshVertex(mObject)

    # base
    BmObject = OpenMaya.MObject()
    sel.getDependNode(1, BmObject)
    baseMFN = OpenMaya.MFnMesh(BmObject)
    baseIt = OpenMaya.MItMeshVertex(BmObject)

    # store tangents and biNormals
    negativeTVec = OpenMaya.MVectorArray()
    baseTVec = OpenMaya.MVectorArray()

    negBiNorVec = OpenMaya.MVectorArray()
    baseBiNorVec = OpenMaya.MVectorArray()

    # get Tangents
    for i in diferenceIndex:
        floatVector = OpenMaya.MVector()
        floatBiNormal = OpenMaya.MVector()
        baseVector = OpenMaya.MVector()
        baseBiNormal = OpenMaya.MVector()

        ptr = util.asIntPtr()
        negativeIt.setIndex(i, ptr)
        faces = OpenMaya.MIntArray()
        negativeIt.getConnectedFaces(faces)

        negativeMFN.getFaceVertexTangent(faces[0], i, floatVector)
        negativeMFN.getFaceVertexBinormal(faces[0], i, floatBiNormal)

        baseMFN.getFaceVertexTangent(faces[0], i, baseVector)
        baseMFN.getFaceVertexBinormal(faces[0], i, baseBiNormal)

        negativeTVec.append(floatVector)
        negBiNorVec.append(floatBiNormal)
        baseTVec.append(baseVector)
        baseBiNorVec.append(baseBiNormal)

    # apply martix transforms
    for n, i in enumerate(diferenceIndex):
        # negative
        normal = OpenMaya.MVector()
        negativeMFN.getVertexNormal(i, normal)
        binormal = negBiNorVec[n]
        binormal.normalize()
        tangent = negativeTVec[n]
        tangent.normalize()
        matrixSpaceNegative = [normal.x, normal.y, normal.z, 0, tangent.x, tangent.y, tangent.z, 0, binormal.x,
                               binormal.y, binormal.z, 0, 0, 0, 0, 1]
        matrixNeg = OpenMaya.MMatrix()
        util.createMatrixFromList(matrixSpaceNegative, matrixNeg)

        matrixNeg3x3 = pm.datatypes.MatrixN([[normal.x, normal.y, normal.z], [tangent.x, tangent.y, tangent.z],
                                             [binormal.x, binormal.y, binormal.z]])

        # base
        normal = OpenMaya.MVector()
        baseMFN.getVertexNormal(i, normal)
        binormal = baseBiNorVec[n]
        binormal.normalize()
        tangent = baseTVec[n]
        tangent.normalize()
        matrixSpaceBase = [normal.x, normal.y, normal.z, 0, tangent.x, tangent.y, tangent.z, 0, binormal.x, binormal.y,
                           binormal.z, 0, 0, 0, 0, 1]
        matrixBas = OpenMaya.MMatrix()
        util.createMatrixFromList(matrixSpaceBase, matrixBas)
        matrixBas3x3 = pm.datatypes.MatrixN([[normal.x, normal.y, normal.z], [tangent.x, tangent.y, tangent.z],
                                             [binormal.x, binormal.y, binormal.z]])


        # diferenceVector
        vectorPosed = positive.getPoint(i) - negative.getPoint(i)
        vectorPosed = OpenMaya.MVector(vectorPosed[0], vectorPosed[1], vectorPosed[2])
        vectorPosedPM = pm.datatypes.MatrixN([vectorPosed[0], vectorPosed[1], vectorPosed[2]])

        # TODO: calculate real vector length
        # cmds.skinPercent( 'skinCluster1', 'akona_body_mesh.vtx[2702]', transform='akona_foot_left_joint', query=True )

        # baseSpace
        vecNegSpace = vectorPosedPM * matrixNeg3x3.inverse()
        vecBaseSpace = vecNegSpace * matrixBas3x3
        # compare vector length form joint position


        # apply diference
        originalPos = base.getPoint(i, 'object')

        VertexPos = [originalPos[0] + vecBaseSpace[0][0], originalPos[1] + vecBaseSpace[0][1], originalPos[2] + vecBaseSpace[0][2]]
        baseDup.setPoint(i, VertexPos, 'object')

    baseDup.getTransform().rename('delta')
    return baseDup


def getDeltaByJointAngle(positive, negative, skinMesh,  joint):
    """
    only one rotated joint
    test, i think it is more precise
    :return:
    """
    diferenceIndex = []
    for i, point in enumerate(positive.getPoints('object')):
        if point != negative.getPoint(i, 'object'):
            diferenceIndex.append(i)

    skinCluster = skinMesh.listConnections(connections=True, type='skinCluster')[0][1]
    skinCluster = pm.PyNode(skinCluster)  # convert to pyNode

    # query angles
    angleQ = joint.getRotation(quaternion=True, space='preTransform')
    worldQ = joint.getRotation(quaternion=True, space='world')
    angleEu = joint.getRotation()  # euler
    angle = math.acos(angleQ[3])*2  # angle Radians
    joint.setRotation([0, 0, 0])
    jointZeroR = joint.getRotation(quaternion=True, space='world')

    #angleQ = angleQ * jointZeroR.invertIt()

    jointMatrix = pm.xform(joint, q=True, m=True, ws=True)
    jointMatrix = pm.datatypes.MatrixN([jointMatrix[0], jointMatrix[1], jointMatrix[2]],
                                       [jointMatrix[4], jointMatrix[5], jointMatrix[6]],
                                       [jointMatrix[8], jointMatrix[9], jointMatrix[10]])

    jointOrient = joint.getOrientation()

    # joint position
    jointPos = joint.getTranslation('world')

    # create base pose
    baseMesh = skinMesh.duplicate(name='%s_delta' % str(skinMesh))[0]
    baseMeshShape = baseMesh.getShape()
    joint.setRotation(angleEu)

    for index in diferenceIndex:
        influence = pm.skinPercent(skinCluster, skinMesh.vtx[index], transform=joint, query=True)
        # influence plus influences of child joints
        joinChild = [str(j) for j in joint.listRelatives(ad=True)]
        jointsInfluence = pm.skinPercent(skinCluster, skinMesh.vtx[index], q=True, transform=None)
        matchJoint = set(joinChild).intersection(set(jointsInfluence))
        for j in matchJoint:
            influence += pm.skinPercent(skinCluster, skinMesh.vtx[index], transform=j, query=True)

        # vector from joint to vertex sculpted
        sculptVector = positive.getPoint(index, 'object')
        sculptVector = pm.datatypes.Vector(sculptVector - jointPos)

        # if influence == 0 don't calculate
        if influence:
            angleA = math.pi - (angle/2 + math.pi/2)
            angleB = math.pi - (angle*influence + angleA)
            # with sin rules get the length of final vector
            lengthFVector = sculptVector.length()*math.sin(angleB)/math.sin(angleA)

            # create relative quaternion to influence
            qW = math.cos(angle*(-influence) / 2)
            util = OpenMaya.MScriptUtil()
            util.createFromDouble(angleQ.x, angleQ.y, angleQ.z, qW)
            ptr = util.asDoublePtr()
            relativeQ = pm.datatypes.Quaternion(ptr)

            rotatedVector = sculptVector.rotateBy(relativeQ)
            rotatedVector.normalize()
            rotatedVector = rotatedVector*lengthFVector

            sculptVector = rotatedVector

        baseMeshShape.setPoint(index, sculptVector + jointPos, 'world')











if __name__ == '__main__':
    extractPosesPoseEditor()
    # deltaCorrective([pm.PyNode('akona_foot_right_joint')], pm.PyNode('PSDAkona'))
    # getDelta(pm.PyNode('positive2').getShape(), pm.PyNode('negative2').getShape(), pm.PyNode('base').getShape())
    # extractPosesPoseEditor()