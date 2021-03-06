import numpy as np
import matplotlib.pyplot as plt
import os, sys
import librosa
import pickle
import hashlib

import h5py
from collections import namedtuple

from audio_lib import calc_MFCC_input, calc_PHN_target
from sound_ds import Sound_DS


class ARCTIC(Sound_DS):
    def __init__(self, cfg_d={}):
        
        self.cfg_d = cfg_d

        if 'hop_length' not in self.cfg_d.keys():
            self.cfg_d['hop_length'] = int(self.cfg_d['hop_length_ms'] * self.cfg_d['sample_rate'] / 1000.0)
            print(" - cfg_d['hop_length'] = {:d}".format(self.cfg_d['hop_length']))

        if 'win_length' not in self.cfg_d.keys():
            self.cfg_d['win_length'] = int(self.cfg_d['win_length_ms'] * self.cfg_d['sample_rate'] / 1000.0)
            print(" - cfg_d['win_length'] = {:d}".format(self.cfg_d['win_length']))

        
        self.ds_path          = cfg_d['ds_path']

        self.random_seed      = cfg_d['random_seed']
        self.verbose          = cfg_d['verbose']

        self.ds_norm          = cfg_d['ds_norm']

        self.n_mfcc           = cfg_d['n_mfcc']         # Cantidad de mfcc en la salida 
        self.n_timesteps      = cfg_d['n_timesteps']    # Cantidad de de pasos temporales para el muestreo  window_sampler

        
        if self.random_seed is not None:
            np.random.seed(self.random_seed)
            
        
        self.sample_rate  = cfg_d['sample_rate']


        self.ds_type_v    = np.array(['TRAIN', 'TEST'])
        self.ds_dialect_v = np.array(['DR'+str(i) for i in range(1,9)])
        self.ds_gender_v  = np.array(['M', 'F'])

        self.ds_phoneme_43_v = np.array(['b', 'd', 'g', 'p', 't', 'k',                 # Stops
                                         'jh', 'ch',                                   # Affricates
                                         's', 'sh', 'z', 'zh', 'f', 'th', 'v', 'dh',   # Fricatives
                                         'm', 'n', 'ng',                               # Nasals
                                         'l', 'r', 'w', 'y', 'hh',                     # Semivowels and Glides
                                         'aa', 'ae', 'ah', 'ao', 'aw', 'ax', 'ay', 'eh', 'er', 'ey', 'ih', 'iy', 'ow', 'oy', 'uh', 'uw', # Vowels
                                         'H#', 'pau', 'ssil'])                         # Others



        self.ds_cache_name  = cfg_d['ds_cache_name']
        phn_mfcc_name_id = hashlib.md5('_'.join([str(cfg_d[k]) for k in ('sample_rate',
                                                                         'pre_emphasis',
                                                                         'hop_length',
                                                                         'win_length',
                                                                         'n_mels',
                                                                         'n_mfcc',
                                                                         'n_fft',
                                                                         'window',
                                                                         'mfcc_normaleze_first_mfcc',
                                                                         'mfcc_norm_factor',
                                                                         'calc_mfcc_derivate',
                                                                         'M_dB_norm_factor',
                                                                         'P_dB_norm_factor',
                                                                         'mean_abs_amp_norm',
                                                                         'clip_output')]).encode()).hexdigest()


        self.spec_cache_name = '.'.join(cfg_d['spec_cache_name'].split('.')[:-1]) + '_' + phn_mfcc_name_id + '.' + cfg_d['spec_cache_name'].split('.')[-1]

        self.ds = None
        if not os.path.exists( os.path.join(self.ds_path, self.ds_cache_name) ) or cfg_d['remake_samples_cache']:
            self.read_dataset_from_disk(self.verbose)        
            self.save_dataset_cache()
        else:
            self.load_dataset_cache()


        self._normalize_ds()

        self.make_phoneme_convertion_dicts()


        if not os.path.exists(os.path.join(self.ds_path, self.spec_cache_name)):
            r = ''
            while not r in ['y', 'n']:
                print(' - ARCTIC, no se encontró el archivo de cache "{}", desea construirlo (y/n):'.format(self.spec_cache_name), end='')
                r = input()
            if r == 'y':
                self.create_spec_cache()
            else:
                print(' - ARCTIC, no se puede continuar sin generar el archivo de cache.', file=sys.stderr)
                return None
                
        return None



    def create_spec_cache(self, cfg_d=None):

        if cfg_d is None:
            cfg_d = self.cfg_d


        if os.path.exists(os.path.join(self.ds_path, self.spec_cache_name)):
            print(' WARNING, create_spec_cache: el archivo "{}" ya existe, para generarlo de nuevo primero se debe eliminar.', file=sys.stderr)
            return None
        
        phn_conv_d = self.phn2ohv
        n_samples  = len(self.ds['wav'])


        print(' - create_spec_cache, Salvando {} cache'.format(self.spec_cache_name))
        
        with h5py.File(os.path.join(self.ds_path, self.spec_cache_name),'w') as ds_h5py:

            grp_mfcc     = ds_h5py.create_group("mfcc")
            grp_mel_dB   = ds_h5py.create_group("mel_dB")
            grp_power_dB = ds_h5py.create_group("power_dB")
            grp_phn      = ds_h5py.create_group("phn")
            

            phn_conv_d = self.phn2ohv
            for i_sample in range(n_samples):
                if self.verbose and i_sample%100==0:
                    print(' - Saved: {} of {} samples'.format(i_sample, n_samples))
                y     = self.ds['wav'][i_sample]
                phn_v = self.ds['phn_v'][i_sample]
                
                mfcc, mel_dB, power_dB = calc_MFCC_input(y,
                                                         sr=cfg_d['sample_rate'],
                                                         pre_emphasis=cfg_d['pre_emphasis'],
                                                         hop_length=cfg_d['hop_length'],
                                                         win_length=cfg_d['win_length'],
                                                         n_mels=cfg_d['n_mels'],
                                                         n_mfcc=cfg_d['n_mfcc'],
                                                         n_fft=cfg_d['n_fft'],
                                                         window=cfg_d['window'],
                                                         mfcc_normaleze_first_mfcc=cfg_d['mfcc_normaleze_first_mfcc'],
                                                         mfcc_norm_factor=cfg_d['mfcc_norm_factor'],
                                                         calc_mfcc_derivate=cfg_d['calc_mfcc_derivate'],
                                                         M_dB_norm_factor=cfg_d['M_dB_norm_factor'],
                                                         P_dB_norm_factor=cfg_d['P_dB_norm_factor'],
                                                         mean_abs_amp_norm=cfg_d['mean_abs_amp_norm'],
                                                         clip_output=cfg_d['clip_output'])

                phn  = calc_PHN_target(y, phn_v, phn_conv_d,
                                       hop_length=cfg_d['hop_length'],
                                       win_length=cfg_d['win_length'])

                assert mfcc.shape[0] == phn.shape[0], '- ERROR, create_spec_cache: para la muestra {}, mfcc.shape[0] != phn.shape[0]'.format(i_sample)
                
                grp_mfcc.create_dataset(    str(i_sample), data=mfcc)
                grp_mel_dB.create_dataset(  str(i_sample), data=mel_dB)
                grp_power_dB.create_dataset(str(i_sample), data=power_dB)
                grp_phn.create_dataset(     str(i_sample), data=phn)

##
        if self.verbose:
            print('Archivo "{}" escrito en disco.'.format(self.spec_cache_name))
                
##                ds_h5py['mfcc'][i_sample] = mfcc
##                ds_h5py['phn'][i_sample] = phn
            
        return None
        

                

            
    def read_dataset_from_disk(self, verbose=False):
        
        self.ds = {'wav':    [],  # Sound wave
                   'spk_id': [],  # Spreaker Id
                   'phn_v':  [],  # Phoneme list
                   'sts_id': []}  # Sentence id


        if verbose:
            print(' - ARCTIC, read_dataset_from_disk, leyendo ARCTIC dataset desde:'.format(self.ds_path))

        n_samples = 0    
        for spk_dir in os.listdir(self.ds_path):
            if verbose:
                print(' - ARCTIC, read_dataset_from_disk, leyendo: "{}"'.format(spk_dir))
                
            if os.path.isdir( os.path.join(self.ds_path, spk_dir) ):

                spk_id = spk_dir.split('_')[-2]

                abs_spk_dir = os.path.join(self.ds_path, spk_dir)
                wav_dir = os.path.join(abs_spk_dir, 'wav')  
                phn_dir = os.path.join(abs_spk_dir, 'lab')

                
                for wav_file_name in sorted( os.listdir(wav_dir) ):
                    if len(wav_file_name) > 3 and wav_file_name[-4:] == '.wav':
                        sts_id = wav_file_name.split('_')[-1].split('.')[0]
                        abs_wav_file_name = os.path.join(wav_dir, wav_file_name)
                        abs_phn_file_name = os.path.join(phn_dir, wav_file_name.replace('wav', 'lab'))
                        
                        wav   = self.read_wav(abs_wav_file_name)
                        phn_v = self.read_phn(abs_phn_file_name)
                        
                        self.ds['wav'].append(wav)
                        self.ds['phn_v'].append(phn_v)
                        self.ds['spk_id'].append(spk_id)
                        self.ds['sts_id'].append(sts_id)

                        n_samples += 1

        for k in self.ds.keys():
            self.ds[k] = np.array(self.ds[k])

        if verbose:
            print(' - ARCTIC, read_dataset_from_disk, DateSet leido ARCTIC, cantidad de archivos leidos: {}'.format(n_samples))

        return None         



    def read_wav(self, file_path='./TEST/DR1/FAKS0/SA1.WAV'):
        y, sr = librosa.load(file_path, sr=self.sample_rate)
        return y

    def read_phn(self, file_path='./TEST/DR1/FAKS0/SA1.PHN'):
        with open(file_path , 'r') as f:
            ml_v = f.readlines()

        phn_v = []
        last = 0
        for ml in ml_v:
            l_v = ml.strip().split()
            if len(l_v) == 3:
                phn_v.append( (last, int(self.sample_rate*float(l_v[0])), l_v[2]) )
                last = phn_v[-1][1]
                
        return phn_v



    def make_phoneme_convertion_dicts(self):
        """ Arma los diccionarios de conversión de phonemes según la agrupación que se quiera usar"""
        
        self.phn2ohv = {} # Conversión de phonema_str a one_hot_vector
        self.phn2idx = {} # Conversión de phonema_str a index
        self.idx2phn = {} # Conversión de index a phonema_str

        for idx, phn in enumerate(self.ds_phoneme_43_v):
            ohv = np.zeros(len(self.ds_phoneme_43_v))
            ohv[idx] = 1.0

            self.phn2ohv[phn] = ohv
            self.phn2idx[phn] = idx
            self.idx2phn[idx] = phn

        self.n_phn = len(self.ds_phoneme_43_v)
    
        return None

    

    
    def _zero_pad(self, *to_pad, pad_len=10):
        ret_v = []
        for spec in to_pad: 
            spec_padded = np.concatenate( [spec, np.zeros( (pad_len, spec.shape[1]) )], axis=0 )
            
            ret_v.append(spec_padded)

        return ret_v
    

    def spec_window_sampler(self, batch_size=32, n_epochs=1, randomize_samples=True, sample_trn=True, prop_val=0.3, ds_filter_d={'spk_id':['bdl','rms','slt','clb']}, yield_idxs=False):
        n_timesteps=self.n_timesteps 
        f_s = self.get_ds_filter(ds_filter_d)
        samples_v = np.arange(f_s.shape[0])[f_s]
        samples_v = np.array( [str(i) for i in samples_v] )

        if prop_val > 0.0:
            np.random.seed(0)# Some seed
            
            idx_v = np.arange(samples_v.shape[0])
            np.random.shuffle(idx_v)

            n_val = int(prop_val*samples_v.shape[0])
            idx_trn = idx_v[:-n_val]
            idx_val = idx_v[-n_val:]

            if sample_trn:
                samples_v = samples_v[idx_trn]
            else:
                samples_v = samples_v[idx_val]

            np.random.seed(self.random_seed)
        
        with h5py.File(os.path.join(self.ds_path, self.spec_cache_name),'r') as ds_h5py:
            mfcc_v     = []
            mel_dB_v   = []
            power_dB_v = []

            n_warning  = 0
            
            idxs_v = []
            for i_epoch in range(n_epochs):
                if randomize_samples:
                    np.random.shuffle(samples_v)
                
                for i_sample in samples_v:
                    spec_len = ds_h5py['mfcc'][i_sample].shape[0]
                    
                    if spec_len <= n_timesteps:
                        # Padding
                        i_s = 0
                        i_e = n_timesteps
                        
                        mfcc     = ds_h5py["mfcc"][i_sample][:]
                        mel_dB   = ds_h5py["mel_dB"][i_sample][:]
                        power_dB = ds_h5py["power_dB"][i_sample][:]
                        
                        pad_len = n_timesteps - spec_len

                        mfcc, mel_dB, power_dB = self._zero_pad(mfcc, mel_dB, power_dB, pad_len=pad_len)
                        
                        if n_warning < 5:
                            print('WARNING: padding!!!'.format(i_sample))
                            n_warning += 1

                    else:
                        # Solamente elegimos un frame por wav
                        i_s = np.random.randint(0, spec_len-n_timesteps)
                        i_e = i_s + n_timesteps
                        
                        mfcc     = ds_h5py["mfcc"][i_sample][i_s:i_e]
                        mel_dB   = ds_h5py["mel_dB"][i_sample][i_s:i_e]
                        power_dB = ds_h5py["power_dB"][i_sample][i_s:i_e]



                    mfcc_v.append( mfcc )
                    mel_dB_v.append( mel_dB )
                    power_dB_v.append( power_dB )
                    
                    idxs_v.append([i_s, i_e, int(i_sample)])
                        

                    if len(mfcc_v) == batch_size:
                        mfcc_v     = np.array(mfcc_v)
                        mel_dB_v   = np.array(mel_dB_v)
                        power_dB_v = np.array(power_dB_v)
                        
                        assert mfcc_v.shape[1] == mel_dB_v.shape[1] == power_dB_v.shape[1] == n_timesteps

                        if yield_idxs:
                            idxs_v = np.array(idxs_v)
                            yield mfcc_v, mel_dB_v, power_dB_v, idxs_v
                        else:
                            yield mfcc_v, mel_dB_v, power_dB_v
                            
                        mfcc_v     = []
                        mel_dB_v   = []
                        power_dB_v = []
                        idxs_v     = []

                        

    def window_sampler(self, batch_size=32, n_epochs=1, randomize_samples=True, sample_trn=True, prop_val=0.3, ds_filter_d={'spk_id':['bdl','rms','slt','clb']}, yield_idxs=False):
        n_timesteps=self.n_timesteps 
        f_s = self.get_ds_filter(ds_filter_d)
        samples_v = np.arange(f_s.shape[0])[f_s]
        samples_v = np.array( [str(i) for i in samples_v] )

        if prop_val > 0.0:
            np.random.seed(0)# Some seed
            
            idx_v = np.arange(samples_v.shape[0])
            np.random.shuffle(idx_v)

            n_val = int(prop_val*samples_v.shape[0])
            idx_trn = idx_v[:-n_val]
            idx_val = idx_v[-n_val:]

            if sample_trn:
                samples_v = samples_v[idx_trn]
            else:
                samples_v = samples_v[idx_val]

            np.random.seed(self.random_seed)
            

        with h5py.File(os.path.join(self.ds_path, self.spec_cache_name),'r') as ds_h5py:
            x_v = []
            y_v = []

            n_warning = 0

            idxs_v = []
            for i_epoch in range(n_epochs):
                if randomize_samples:
                    np.random.shuffle(samples_v)

                for i_sample in samples_v:
##                    print('sample', i_sample)
##                    print(mfcc.shape, phn.shape)

                    spec_len = ds_h5py['mfcc'][i_sample].shape[0]
                    if spec_len <= n_timesteps:
                        # Padding
                        i_s = 0
                        i_e = n_timesteps
                        
                        mfcc = ds_h5py['mfcc'][i_sample][:]
                        phn  = ds_h5py['phn'][i_sample][:]
                        
                        pad_len = n_timesteps - spec_len

                        mfcc, phn = self._zero_pad(mfcc, phn, pad_len=pad_len)

                        # Makeing phoneme target
                        idx = arctic.phn2idx['pau']
                        phn[-pad_len:,idx] = 1.0
                        
                        if n_warning < 5:
                            print('WARNING: padding!!!'.format(i_sample))
                            n_warning += 1

                    else:
                        
                        # Solamente elegimos un frame por wav
                        # TODO: llevar la cuenta de los frames elegidos como i_sample asi siempre elegimos uno distinto
                        i_s = np.random.randint(0, spec_len-n_timesteps)
                        i_e = i_s + n_timesteps
                        
                        mfcc = ds_h5py['mfcc'][i_sample][i_s:i_e]
                        phn  = ds_h5py['phn'][i_sample][i_s:i_e]

                    x_v.append( mfcc )
                    y_v.append( phn )
                    idxs_v.append([i_s, i_e, int(i_sample)])

                    if len(x_v) == batch_size:
                        x_v = np.array(x_v)
                        y_v = np.array(y_v)
                        
                        assert x_v.shape[1] == y_v.shape[1] == n_timesteps

                        if yield_idxs:
                            idxs_v = np.array(idxs_v)
                            yield x_v, y_v, idxs_v
                        else:
                            yield x_v, y_v
                        x_v = []
                        y_v = []
                        idxs_v = []
                            

    

    
    def calc_class_weights(self, clip=(0,10), ds_filter_d={'spk_id':['bdl','rms','slt','clb']}):
        f_s = self.get_ds_filter(ds_filter_d)
        samples_v = np.arange(f_s.shape[0])[f_s]

        samples_v = [str(i) for i in samples_v]

        counter_v = None
        with h5py.File(os.path.join(self.ds_path, self.spec_cache_name),'r') as ds_h5py:
            for i_s in samples_v:
                if counter_v is None:
                    counter_v = np.sum(ds_h5py['phn'][str(i_s)], axis=0)
                else:
                    counter_v += np.sum(ds_h5py['phn'][str(i_s)], axis=0)

        n_samples = int(np.sum(counter_v))
        
        majority = np.mean(counter_v)
        cw_d = {cls: float(majority/count) if count > 0 else 1.0 for cls, count in enumerate(counter_v)}

        if clip is not None:
            for k in cw_d.keys():
               cw_d[k] = np.clip(cw_d[k], clip[0], clip[1])
               
        return cw_d, n_samples


    
# 6 119 737

if __name__ == '__main__':
    import time
    
    if os.name == 'nt':
        ds_path = r'G:\Downloads\ARCTIC\cmu_arctic'
    else:
        ds_path = './../data_sets/ARCTIC/cmu_arctic'


    ds_cfg_d = {'ds_path':ds_path,
                'ds_norm':(0.0, 1.0),
                'remake_samples_cache':False,
                'random_seed':0,
                'ds_cache_name':'arctic_cache.pickle',
                'spec_cache_name':'spec_cache.h5py',
                'verbose':True,

                'sample_rate':16000,  #Frecuencia de muestreo los archivos de audio Hz

                'pre_emphasis': 0.97,
                
                'hop_length_ms':   5.0, # 2.5ms = 40c | 5.0ms = 80c (@ 16kHz)
                'win_length_ms':  25.0, # 25.0ms = 400c (@ 16kHz)
                'n_timesteps':   400, # 800ts*(win_length_ms=2.5ms)= 2000ms  Cantidad de hop_length_ms en una ventana de prediccion.
                
                'n_mels':80,
                'n_mfcc':40,
                'n_fft':None, # None usa n_fft=win_length
                
                'window':'hann',
                'mfcc_normaleze_first_mfcc':True,
                'mfcc_norm_factor': 0.01,
                'calc_mfcc_derivate':False,
                'M_dB_norm_factor':0.01,
                'P_dB_norm_factor':0.01,
                
                'mean_abs_amp_norm':0.003,
                'clip_output':True}



    arctic = ARCTIC(ds_cfg_d)

##    mfcc_batch, phn_v_batch, idxs_v_batch = next(iter(arctic.window_sampler(10, 1, yield_idxs=True, ds_filter_d={'spk_id':'bdl'})))
##    for mfcc, phn_v, idxs_v in zip(mfcc_batch, phn_v_batch, idxs_v_batch):
####        print(idxs_v)
##        arctic.spec_show(mfcc, phn_v, idxs_v)


    mfcc_batch, mel_batch, stft_batch, idxs_v_batch = next(iter(arctic.spec_window_sampler(50,1, yield_idxs=True)))
    for mfcc, mel, stft, idxs_v in zip(mfcc_batch, mel_batch, stft_batch, idxs_v_batch):
        print(idxs_v)
        arctic.spec_show(stft, None, idxs_v)
        
        

##    for i_sample in range(0, len(arctic.ds['wav'])):
##        m, _, _ = calc_MFCC_input(arctic.ds['wav'][i_sample])
##        p    = calc_PHN_target(arctic.ds['wav'][i_sample], arctic.ds['phn_v'][i_sample], arctic.phn2ohv)
##        
##
##        for a, b, p_str in arctic.ds['phn_v'][i_sample]:
##            print('{:5d} -> {:5d}   :  delta:{:5d} :  {}'.format(a//40,b//40, (b-a)//40, p_str))
##
##
##        arctic.spec_show(m, p)
##
##        break

##    
##    t0 = time.time()
##    n_batch=0
##    for mfcc, phn in arctic.window_sampler(batch_size=32, n_epochs=1, ds_filter_d={}):
##        n_batch += 1
####        print(mfcc.shape)
####        print(phn.shape)
##    print(' Muestreo completo en {:0.02f} s, n_batches={}'.format(time.time() - t0, n_batch))

        
##    for x, y in arctic.phoneme_sampler():
##        for i in range(len(x)):
##            if np.argmax(y[i]) == np.argmax(arctic.phoneme_d['ae']):
##                arctic.play(x[i])
##                input()

    
    
##    for a, b, p in phn_v:
##        y_aux = np.concatenate( (np.zeros(arctic.sample_rate), y[a:b] ))
##        y_aux = np.concatenate([y_aux,y_aux,y_aux])
##        _=plt.plot(y_aux)
##        arctic.play_sound(y_aux)
##        print(p)
##        plt.show()
