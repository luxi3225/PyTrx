# -*- coding: utf-8 -*-
'''
PyTrx (c) by Penelope How, Nick Hulton, Lynne Buie

PyTrx is licensed under a
Creative Commons Attribution 4.0 International License.

You should have received a copy of the license along with this
work. If not, see <http://creativecommons.org/licenses/by/4.0/>.


PYTRX EXAMPLE DENSE VELOCITY DRIVER (EXTENDED VERSION)

This script is part of PyTrx, an object-oriented programme created for the 
purpose of calculating real-world measurements from oblique images and 
time-lapse image series.

This driver calculates surface velocities using modules in PyTrx at Kronebreen,
Svalbard, for a subset of the images collected during the 2014 melt season. 
Specifically this script performs feature-tracking through sequential daily 
images of the glacier to derive surface velocities (spatial average, 
individual point displacements and interpolated velocity maps) which have been 
corrected for image distortion and motion in the camera platform (i.e. image
registration).

This script is a class-independent version of 'driver_velocity1.py'. 
The functions used here do not depend on class object inputs and can be run as 
stand-alone functions.

This script has been included in order to provide the user with a more detailed 
overview of PyTrx's functionality beyond its object-oriented structure. It also 
allows flexible intervention and adaptation where needed. 
'''

#Import packages
import sys
import numpy as np
import cv2
import glob
import cv2
import math
import time
from scipy.sparse import lil_matrix
from scipy.optimize import least_squares
import matplotlib.pyplot as plt
from pathlib import Path

#Import PyTrx packages
sys.path.append('../')
from CamEnv import setProjection, projectXYZ, getRotation
from Velocity import calcDenseHomography, calcSparseHomography, calcDenseVelocity, readDEMmask
from DEM import load_DEM
import FileHandler
import Utilities 
 
#------------------------   Define inputs/outputs   ---------------------------

print('\nDEFINING DATA INPUTS')

#Camera name, location (XYZ) and pose (yaw, pitch, roll)
camname = 'KR2_2014'
camloc = np.array([447948.820, 8759457.100, 407.092])

#campose = np.array([4.80926, 0.05768, 0.14914]) 
campose = np.array([4.80926, 0.05768, 0.14914]) 


#Define image folder and image file type for velocity tracking
imgFiles = '../Examples/images/KR2_2014_subset/*.JPG'

#Define calibration images and chessboard dimensions (height, width)
calibPath = '../Examples/camenv_data/calib/KR1_2014_1.txt'

#Load DEM from path
DEMpath = '../Examples/camenv_data/dem/KR_demsmooth.tif'        

#Define masks for velocity and homography point generation
vmaskPath = '../Examples/camenv_data/masks/KR2_2014_dem_vmask.jpg'      
hmaskPath = '../Examples/camenv_data/invmasks/KR2_2014_inv.jpg'    

#Define reference image (where GCPs have been defined)
refimagePath = '../Examples/camenv_data/refimages/KR2_2014.JPG'

#Define GCPs (world coordinates and corresponding image coordinates)
GCPpath = '../Examples/camenv_data/gcps/KR2_2014.txt'


print('\nDEFINING DATA OUTPUTS')

#Velocity output
target1 = '../Examples/results/velocity3/velo_output.csv'

#Homography output
target2 = '../Examples/results/velocity3/homography.csv'

#Shapefile output (with WGS84 projection)
target3 = '../Examples/results/velocity3/shpfiles/'     
projection = 32633

#Plot outputs
target4 = '../Examples/results/velocity3/imgfiles/'
interpmethod='linear'                                 #nearest/cubic/linear
cr1 = [445000, 452000, 8754000, 8760000]              #DEM plot extent   


#--------------------------   Define parameters   -----------------------------

#DEM parameters 
DEMdensify = 2                      #DEM densification factor (for smoothing)

#Image enhancement paramaters
band = 'L'                          #Image band extraction (R, B, G, or L)
equal = True                        #Histogram equalisation?

#Velocity parameters
vwin = (25,25)                      #Tracking window size
vback = 1.0                         #Back-tracking threshold  
vmax = 50000                        #Maximum number of points to seed
vqual = 0.1                         #Corner quality for seeding
vmindist = 5.0                      #Minimum distance between seeded points
vminfeat = 4                        #Minimum number of seeded points to track
                           
#Homography parameters
hwin = (25,25)                      #Stable pt tracking window size
hmethod = cv2.RANSAC                #Homography calculation method 
                                    #(cv2.RANSAC, cv2.LEAST_MEDIAN, or 0)
hreproj = 5.0                       #Maximum allowed reprojection error
hback = 0.5                         #Back-tracking threshold
herr = True                         #Calculate tracking error?
hmax = 50000                        #Maximum number of points to seed
hqual = 0.5                         #Corner quality for seeding
hmindist = 5.0                      #Minimum distance between seeded points
hminfeat = 4                        #Minimum number of seeded points to track


#----------------------   Set up camera environment   -------------------------

print('\nLOADING DEM')
dem = load_DEM(DEMpath)
dem=dem.densify(DEMdensify)


print('\nLOADING GCPs')
GCPxyz, GCPuv = FileHandler.readGCPs(GCPpath)


print('\nLOADING CALIBRATION')
calib_out = FileHandler.readMatrixDistortion(calibPath)
matrix=np.transpose(calib_out[0])                           #Get matrix
tancorr = calib_out[1]                                      #Get tangential
radcorr = calib_out[2]                                      #Get radial
focal = [matrix[0,0], matrix[1,1]]                          #Focal length
camcen = [matrix[0,2], matrix[1,2]]                         #Principal point
 
distort = np.hstack([radcorr[0][0], radcorr[0][1],          #Compile distortion
                     tancorr[0][0], tancorr[0][1],          #parameters
                     radcorr[0][2]])


print('\nLOADING IMAGE FILES')
imagelist = sorted(glob.glob(imgFiles))
im1 = FileHandler.readImg(imagelist[0], band, equal)
imn1 = Path(imagelist[0]).name


print('\nOPTIMISING CAMERA ENVIRONMENT')
GCPxyz1 = np.array(GCPxyz, dtype=np.float32)
GCPuv1 = np.array(GCPuv, dtype=np.float32)
rvec1 = getRotation(campose)
tvec1 = np.zeros((3,1))
flag=cv2.SOLVEPNP_ITERATIVE

#retval, rvec2, tvec2= cv2.solvePnP(GCPxyz1, GCPuv1, matrix, distort, None, 
#                                   None, flags=flag)

retval, rvec2, tvec2, inliers = cv2.solvePnPRansac(GCPxyz1, GCPuv1, matrix, distort)

rvec3 = cv2.Rodrigues(rvec2)[0]




        
#https://scipy-cookbook.readthedocs.io/items/bundle_adjustment.html


print('\nCOMPILING TRANSFORMATION PARAMETERS')
projvars = [camloc, campose, radcorr, tancorr,              #Projection params
            focal, camcen, refimagePath]  
 
invprojvars = setProjection(dem, camloc, campose,           #Inverse projection
                            radcorr, tancorr, focal,        #params
                            camcen, refimagePath) 

campars = [dem, projvars, invprojvars]                      #Compiled parameters


print('\nBEGINNING OPTIMISATION')
def computeResiduals(params, stable, GCPuv, refimagePath, optimise='YPR'):
    
    if optimise == 'YPR':
        campose = params      
        camloc, radcorr, tancorr, focal, camcen, GCPxyz = stable
        
    elif optimise == 'CAM':
        camloc = params[0:3]
        campose = params[3:6]
        radcorr = params[6:9]
        tancorr = params[9:11]
        focal = params[11:13]
        camcen = params[13:15]
        GCPxyz = stable        
        
    elif optimise == 'ALL':
        camloc = params[0:3]
        campose = params[3:6]
        radcorr = params[6:9]
        tancorr = params[9:11]
        focal = params[11:13]
        camcen = params[13:15]
        GCPxyz = np.array(params[15:]).reshape(-1, 3)

    else:       
        camloc, campose, radcorr, tancorr, focal, camcen, GCPxyz = stable
            
    GCPxyz_proj,depth,inframe = projectXYZ(camloc, campose, radcorr, tancorr, 
                                           focal, camcen, refimagePath, GCPxyz)
    residual=[]
    for i in range(len(GCPxyz_proj)):
        residual.append(np.sqrt((GCPxyz_proj[i][0]-GCPuv[i][0])*
                                (GCPxyz_proj[i][0]-GCPuv[i][0])+
                                (GCPxyz_proj[i][1]-GCPuv[i][1])*
                                (GCPxyz_proj[i][1]-GCPuv[i][1])))  
    residual = np.array(residual)

    return residual

def optimiseCamera(optimise, camloc, campose, radcorr, tancorr, focal, camcen, 
                   GCPxyz, GCPuv, refimagePath, show=False):

    #Compute GCP residuals with original camera info
    stable = [camloc, campose, radcorr, tancorr, focal, camcen, GCPxyz]    
    res0 = computeResiduals(None, stable, GCPuv, refimagePath, optimise=None)
    GCPxyz_proj0,depth,inframe = projectXYZ(camloc, campose, radcorr, tancorr, 
                                           focal, camcen, refimagePath, GCPxyz)

    if optimise=='YPR':
        params = campose
        stable = [camloc, radcorr, tancorr, focal, camcen, GCPxyz]
    
    elif optimise=='CAM':
        params = np.concatenate((camloc, campose, radcorr.flatten(), 
                                 tancorr.flatten(), np.array(focal), 
                                 np.array(camcen)))
        stable = GCPxyz        
        
    elif optimise=='ALL':
        params = np.concatenate((camloc, campose, radcorr.flatten(), 
                                 tancorr.flatten(), np.array(focal), 
                                 np.array(camcen), GCPxyz.flatten()))
        stable=None
        
            
    print('Beginning optimisation...')
    out = least_squares(computeResiduals, params, method='trf', ftol=1e-08, 
                        verbose=2, args=(stable, GCPuv, refimagePath, optimise))

    if optimise=='YPR':
        campose = out.x
        
    elif optimise=='CAM':
        camloc = out.x[0:3]
        campose = out.x[3:6]
        radcorr = out.x[6:9]
        tancorr = out.x[9:11]
        focal = out.x[11:13]
        camcen = out.x[13:15]  
        
    elif optimise=='ALL':       
        camloc = out.x[0:3]
        campose = out.x[3:6]
        radcorr = out.x[6:9]
        tancorr = out.x[9:11]
        focal = out.x[11:13]
        camcen = out.x[13:15]
        GCPxyz = out.x[15:].reshape(-1, 3)

    if out.success is True:
        print('Optimisation successful')
        GCPxyz_proj1,depth,inframe = projectXYZ(camloc, campose, radcorr, tancorr, 
                                           focal, camcen, refimagePath, GCPxyz)   
    
        res1=[]
        for i in range(len(GCPxyz_proj1)):
            res1.append(np.sqrt((GCPxyz_proj1[i][0]-GCPuv[i][0])*
                               (GCPxyz_proj1[i][0]-GCPuv[i][0])+
                               (GCPxyz_proj1[i][1]-GCPuv[i][1])*
                               (GCPxyz_proj1[i][1]-GCPuv[i][1])))
    
        print('Original px residuals (average): ' + str(np.mean(res0)))        
        print('Optimised px residuals (average): ' + str(np.mean(res1)))
        
        if show == True:
            fig, (ax1) = plt.subplots(1)
            ax1.imshow(im1, cmap='gray')
            ax1.scatter(GCPuv[:,0], GCPuv[:,1], color='red', label='UV')
            ax1.scatter(GCPxyz_proj0[:,0], GCPxyz_proj0[:,1], color='green', label='Original XYZ')
            ax1.scatter(GCPxyz_proj1[:,0], GCPxyz_proj1[:,1], color='blue', label='Optimised XYZ')
            ax1.legend()
            plt.show()
        
    else:
        print('Optimisation failed')



#    return camloc, campose, radcorr, tancorr, focal, camcen, GCPxyz, GCPuv, refimagePath

optimiseCamera('CAM', camloc, campose, radcorr, tancorr, focal, camcen, 
                GCPxyz, GCPuv, refimagePath, show=True)

sys.exit(1)

print('\nLOADING MASKS')
print('Defining velocity mask')
vmask = readDEMmask(dem, im1, invprojvars, vmaskPath)

print('Defining homography mask')
hmask = FileHandler.readMask(None, hmaskPath)
#hmask = readDEMmask(dem, im1, invprojvars, hmaskPath)


#--------------------   Plot camera environment info   ------------------------

print('\nPLOTTING CAMERA ENVIRONMENT INFO')

##Load reference image
#refimg = FileHandler.readImg(refimagePath) 
#imn = Path(refimagePath).name

##Show GCPs
#Utilities.plotGCPs([GCPxyz, GCPuv], refimg, imn, 
#                   dem, camloc, extent=None)          

##Show Prinicpal Point in image
#Utilities.plotPrincipalPoint(camcen, refimg, imn)

#Show corrected and uncorrected image

#Utilities.plotCalib(matrix, distort, refimg, imn)



#----------------------   Calculate velocities   ------------------------------

print('\nCALCULATING VELOCITIES')

#Create empty output variables
velo = []                                     
homog = []

#Cycle through image pairs (numbered from 0)
for i in range(len(imagelist)-1):

    #Re-assign first image in image pair
    im0=im1
    imn0=imn1
                    
    #Get second image (corrected) in image pair
    im1 = FileHandler.readImg(imagelist[i+1], band, equal)
    imn1 = Path(imagelist[i+1]).name                                                       
    
    
    print('\nProcessing images: ' + str(imn0) + ' and ' + str(imn1))
        
#    #Calculate homography between image pair
    print('Calculating homography...')
#    hgrid = [100,100]
#    htemp=30
#    hsearch=100    
#    trmethod='cv2.TM_CCORR_NORMED' 
#    homogmeth=cv2.RANSAC
#    reproj=5.0
#    hmin=4.0
#    hg = calcDenseHomography(im0, im1, hmask, [matrix,distort], hgrid, htemp, 
#                             hsearch, dem, projvars, trmethod, 
#                             homogmeth, reproj, hmin)   
    

    hg = calcSparseHomography(im0, im1, hmask, [matrix,distort], hmethod, hreproj, 
                              hwin, hback, hminfeat, [hmax, hqual, hmindist])
    homog.append(hg)
                             
    #Calculate velocities between image pair
    print('Calculating velocity...')
    
    griddistance = [500,500]
    templatesize=30
    searchsize=100    
    method='cv2.TM_CCORR_NORMED'  
    threshold=2.0
    min_features=4.0

    vl = calcDenseVelocity(im0, im1, griddistance, method, templatesize, 
                           searchsize, vmask, [matrix,distort], 
                           [hg[0],hg[3]], campars, threshold)   

#    vl = calcDenseVelocity(im0, im1, griddistance, method, templatesize, 
#                           searchsize, demmask, None, None, campars, threshold)  
    velo.append(vl)             

#---------------------------  Export data   -----------------------------------

print('\nWRITING DATA TO FILE')

#Get all image names
names=[]
for i in imagelist:
    names.append(Path(i).name)

#Extract xyz velocities, uv velocities, and xyz0 locations
xyzvel=[item[0][0] for item in velo] 
xyzerr=[item[0][3] for item in velo]
uvvel=[item[1][0] for item in velo]
xyz0=[item[0][1] for item in velo]

#Write out velocity data to .csv file
FileHandler.writeVeloFile(xyzvel, uvvel, homog, names, target1) 

#Write homography data to .csv file
FileHandler.writeHomogFile(homog, names, target2)

#Write points to shp file                
FileHandler.writeVeloSHP(xyzvel, xyzerr, xyz0, names, target3, projection)       
#
#
#----------------------------   Plot Results   --------------------------------

print('\nPLOTTING OUTPUTS')

#Extract uv0, uv1corr, xyz0 and xyz1 locations 
uv0=[item[1][1] for item in velo]
uv1corr=[item[1][2] for item in velo]
uverr=[item[1][4] for item in velo]
xyz0=[item[0][1] for item in velo]
xyz1=[item[0][2] for item in velo]


#Cycle through data from image pairs   
for i in range(len(xyz0)):
    
    #Get image from sequence
    im=FileHandler.readImg(imagelist[i], band, equal)

    #Correct image for distortion
    newMat, roi = cv2.getOptimalNewCameraMatrix(matrix, distort, 
                                                (im.shape[1],im.shape[0]), 
                                                1, (im.shape[1],im.shape[0])) 
    im = cv2.undistort(im1, matrix, distort, newCameraMatrix=newMat)
    
    #Get image name
    imn = Path(imagelist[i]).name
    print('Visualising data for ' + str(imn))
        
    #Plot uv velocity points on image plane  
    Utilities.plotVeloPX(uvvel[i], uv0[i], uv1corr[i], im, show=True, 
                         save=None)

#    Utilities.plotVeloPX(uverr[i], uv0[i], uv1corr[i], im, show=True, 
#                         save=target4+'uverr_'+imn)
#    
#    uvsnr=uverr[i]/uvvel[i]
#    Utilities.plotVeloPX(uvsnr, uv0[i], uv1corr[i], im, show=True, 
#                         save=target4+'uvsnr_'+imn)    


    #Plot xyz velocity points on dem  
    Utilities.plotVeloXYZ(xyzvel[i], xyz0[i], xyz1[i], dem, show=True, 
                          save=None)

#    Utilities.plotVeloXYZ(xyzerr[i], xyz0[i], xyz1[i], dem, show=True, 
#                          save=target4+'xyzerr_'+imn)    
                
#    #Plot interpolation map
#    grid, pointsextent = Utilities.interpolateHelper(xyzvel[i], xyz0[i], 
#                                                     xyz1[i], interpmethod)
#    Utilities.plotInterpolate(grid, pointsextent, dem, show=True, 
#                              save=target4+'interp_'+imn)  

    
#------------------------------------------------------------------------------
print('\nFinished')