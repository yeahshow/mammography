from os import listdir, makedirs
from os.path import isfile, isdir, join, exists, dirname
import os
import pydicom
from pydicom.dataset import FileDataset
from pydicom.multival import MultiValue
from app.dcmconv import get_LUT_value, get_PIL_mode, get_rescale_params
import csv
import numpy as np
from PIL import Image
from PIL.ImageOps import invert
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import errno
from app.mptqdm import parallel_process

import cv2
import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as transforms
from DensenetModels import DenseNet121
import matplotlib.pyplot as plt
from torchsummary import summary




def read_dcm_to_image(ds_or_file):
    if isinstance(ds_or_file, FileDataset):
        ds = ds_or_file
        debug_name = ds.get('AccessionNumber', 'No AccNo available')
    elif isinstance(ds_or_file, str):
        ds = pydicom.dcmread(ds_or_file)
        debug_name = ds_or_file
    else:
        raise

    try:
        im_arr = ds.pixel_array
    except AttributeError as e:
        print('{}: ds.pixel_array error. {}'.format(debug_name, str(e)))

    rescale_intercept, rescale_slope = get_rescale_params(ds)
    width = ds.get('WindowWidth', None)
    center = ds.get('WindowCenter', None)
    data = get_LUT_value(im_arr, width, center, rescale_intercept, rescale_slope)
    mode = get_PIL_mode(ds)
    img = Image.fromarray(data, mode)

    return img

def do_convert(filename, img_out_path, img_out_width=224, img_out_square=True, use_ori_fname=False):
    #print('filename:'+filename)  
    ori_fname = os.path.splitext(os.path.basename(filename))[0]+ os.path.splitext(os.path.basename(filename))[1]
    #print("ori_fname"+ori_fname)
    ds = pydicom.dcmread(filename)
    img_an = ds.AccessionNumber

    # Debug Info
    ds_an = ds.AccessionNumber if 'AccessionNumber' in ds else None
    ds_pi = ds.PhotometricInterpretation if 'PhotometricInterpretation' in ds else None
    ds_ww = ds.WindowWidth if 'WindowWidth' in ds else None
    ds_wc = ds.WindowCenter if 'WindowCenter' in ds else None
    ds_ri = ds.RescaleIntercept if 'RescaleIntercept' in ds else None
    ds_rs = ds.RescaleSlope if 'RescaleSlope' in ds else None
    ds_uid = ds.SOPInstanceUID if 'SOPInstanceUID' in ds else None
    #print(filename, "AccNo:", ds_an, "PI:", ds_pi, "WW:", ds_ww, "WC:", ds_wc, "RI:", ds_ri, "RS:", ds_rs)
  
          
    img_out_fullpath = join(img_out_path, ds_uid + '.png')
    if not exists(dirname(img_out_fullpath)):
        try:
            makedirs(dirname(img_out_fullpath))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

    try:
        img = read_dcm_to_image(ds)
    except:
        return
    
    small_img = img.convert('RGB')  
    small_img.save(img_out_fullpath)



def main():
  
    projectPTH=os.path.dirname(os.path.abspath(__file__))
   
    
  
    acname="RF09716849340001"                           
                               
    pathModel_1=projectPTH+"/models/m-14052020-042153_003.pth.tar"
    pathModel_2=projectPTH+"/models/m-14052020-061123_78.pth.tar"
    transCrop=224  
    
    Cdir_accno=projectPTH+"/BIRADS_1/"+acname

    
    img_path= Cdir_accno+"/DICOM"
    
    
    if not exists(img_path):
        makedirs(img_path)
        print ("請將dicom放入這裡:",img_path)
       
    
    
    img_out_path=Cdir_accno+"/PNG"
   
    if not exists(img_out_path):
        makedirs(img_out_path)
        
       
    
    HEATMAP_out_path=Cdir_accno+"/HEATMAP"
    
    
    if not exists( HEATMAP_out_path):
        makedirs( HEATMAP_out_path)
    

    
    
    img_out_width = 224
    img_out_square = False
    use_ori_fname =  True
    t_start = time.time()

    if isfile(img_path):       
        do_convert(img_path, img_out_path, img_out_width, img_out_square,False)
    elif isdir(img_path):
          filesa = listdir(img_path)         
          for f in filesa:
            fullpath= join(img_path, f)           
            if isfile(fullpath):              
                print ("File name:"+fullpath) 
                files = [join(img_path, f) for f in listdir(img_path) if isfile(join(img_path, f))] 
                arr = [{'filename': f, 'img_out_path': img_out_path, 'img_out_width': img_out_width, 'img_out_square': img_out_square} for f in files]
                parallel_process(arr, do_convert, use_kwargs=True)
            elif isdir(fullpath):                      
                img_out_path2=join(img_out_path, f)              
                files = [join(fullpath, f) for f in listdir(fullpath) if isfile(join(fullpath, f))]                   
                arr = [{'filename': f, 'img_out_path': img_out_path2, 'img_out_width': img_out_width, 'img_out_square': img_out_square,'use_ori_fname':True} for f in files]
                parallel_process(arr, do_convert, use_kwargs=True)
     
    
    
  

    
    filesa = listdir(img_out_path)   
    print(img_out_path)      
    for f in filesa:
        pathInputImage=img_out_path+"/"+f
        pathOutputFile=HEATMAP_out_path+"/"+f
        HeatmapGenerator(pathModel_1, pathModel_2,transCrop,pathInputImage,pathOutputFile)     
       

    t_end = time.time()
    t_total = t_end - t_start
    
    
    print("Total Time: ", t_total)
    
    


class HeatmapGenerator ():
    
    def __init__ (self, pathModel_1,pathModel_2,transCrop,pathInputImage,pathOutputFile):
        
        checkpoint_1 = torch.load(pathModel_1, map_location=lambda storage, loc: storage)
       
         
        model =DenseNet121(2,False).cpu()
        model = torch.nn.DataParallel(model).cpu()
        model.load_state_dict(checkpoint_1['state_dict'],False)    
       
        self.model = model.module.densenet121.features        
        self.model.eval()
       
    
    #---- Initialize the weights
        self.weights = list(self.model.parameters())[-2]
                  
   
        normalize = transforms.Normalize([0.4914, 0.4822, 0.4465], [0.229, 0.224, 0.225])
      
        transformList = []
        transformList.append(transforms.Resize((1152,896),interpolation=2))
        #transformList.append(transforms.Resize(transCrop))
        #transformList.append(transforms.CenterCrop(transCrop))
        transformList.append(transforms.ToTensor())
        transformList.append(normalize)  
        
        #print(pathInputImage)
        self.transformSequence = transforms.Compose(transformList)
        img = Image.open(pathInputImage)        
        img = img.convert('RGB') 
        
        img = self.transformSequence(img)
        img = img.unsqueeze(0)
        device = torch.device("cpu")
        img = img.to(device)
              
        input = torch.autograd.Variable(img)
        
        self.model.cpu()
        output = self.model(input.cpu())
          #---- Generate heatmap
        heatmap = None
        #print(torch.max(self.weights))
        
        for i in range (0, len(self.weights)):
            # print(self.weights)
            map = output[0,i,:,:]
            if i == 0: heatmap = self.weights[i] * map
            else: heatmap += self.weights[i] * map
        
        #---- Blend original and heatmap 
        npHeatmap = heatmap.cpu().data.numpy()

        imgOriginal = cv2.imread(pathInputImage, 1)
        imgOriginal = cv2.resize(imgOriginal, (transCrop, transCrop),interpolation=cv2.INTER_LINEAR)
        
        cam = npHeatmap / np.max(npHeatmap)
        
        cam = cv2.resize(cam, (transCrop, transCrop))
        heatmap = cv2.applyColorMap(np.uint8(255*cam), cv2.COLORMAP_JET)              
        img = heatmap * 0.5 + imgOriginal  
        print(pathOutputFile)           
        cv2.imwrite(pathOutputFile, img)
        
        
        
        checkpoint_2 = torch.load(pathModel_2, map_location=lambda storage, loc: storage)
        model2 =DenseNet121(2,False).cpu()
        model2 = torch.nn.DataParallel(model2).cpu()
        model2.load_state_dict(checkpoint_2['state_dict'],False)                
        model2.eval()
  
    
        transformList2 = []       
        transformList2.append(transforms.ToTensor())        
   
        transformSequence2 = transforms.Compose(transformList2)
        img2 = Image.open(pathOutputFile)        
     
        
        img2 = transformSequence2(img2)
        img2 = img2.unsqueeze(0)
        device = torch.device("cpu")
        img2 = img2.to(device)
        
        classes = ('NORMAL', 'Mammo Mass')
               
        print('\n')
        print(pathInputImage)
        print('\n')
        with torch.no_grad():
            py = model2(img2)
            _, predicted = torch.max(py, 1)  # 获取分类结果
            classIndex_ = predicted[0]
            print('预测结果', py)
            print(classes[int(classIndex_)])
        print('\n')

if __name__ == "__main__":
    main()
