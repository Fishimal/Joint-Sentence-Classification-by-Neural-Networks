import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from collections import Counter
from more_itertools import take
import collections
import itertools
from sklearn.model_selection import train_test_split
from tqdm.notebook import tqdm 
import re
import numpy as np
import json
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

nltk.download("stopwords")
STOPWORDS = stopwords.words("english")
porter = PorterStemmer()


class TC_UTILS(object):

    def __init__(self) -> None:
        self.TRAIN_SIZE = 0.7
        self.VAL_SIZE = 0.20
        self.TEST_SIZE = 0.10

    def render_lines(self,file):
        with open(file, "r") as fl:
            return fl.readlines()

    def pre_processor(self,filename):
        """Returns a dictionary list with all the information regarding each line in the file
        Args:
            filename (string): Name of the file
        Returns:
            A dictionary containing the line number, target , content of the line and the total nos of lines 
        """
        in_lines = self.render_lines(filename)
        abs_lines = ''
        abs_samples = []

        for line in in_lines:
            if line.startswith('###'):
                abstract_id = line
                abs_lines = ''
            elif line.isspace():
                abs_lines_split = abs_lines.splitlines()
            
                for abs_ln_num, ab_line in enumerate(abs_lines_split):
                    line_resp = {}
                    target_split = ab_line.split('\t')
                    line_resp['target'] = target_split[0]
                    line_resp['text'] = target_split[1].lower()
                    line_resp['line_number'] = abs_ln_num
                    line_resp['total_lines'] = len(abs_lines_split) - 1
                    abs_samples.append(line_resp)
            
            else:
                abs_lines += line

        return abs_samples

    def nltk_preprocessor(self, sentence, stopwords=STOPWORDS):
        """preprocessing the data based on nltk STOPWORDS

        Args:
            sentence (string): The string or the sentence that is to be passed 

        Returns:
            sentence (string): The pre proceesed result from the function 
        """
        # Lower
        sentence = sentence.lower()

        # getting rid of the stop words
        pt = re.compile(r"\b(" + r"|".join(stopwords) + r")\b\s*")
        sentence = pt.sub("", sentence)

        # case 1 :: paranthesis cases
        sentence = re.sub(r"\([^)]*\)", "", sentence)

        # case 2 :: spaces and filters 
        sentence = re.sub(r"([-;;.,!?<=>])", r" \1 ", sentence)
        # case 3 :: non alphanumeric characters
        sentence = re.sub("[^A-Za-z0-9]+", " ", sentence) 
        # case 4 :: multiple spaces
        sentence = re.sub(" +", " ", sentence)  
        sentence = sentence.strip()

        print (STOPWORDS[:5])

        return sentence

    
    def data_splitter(self, X, y, train_size):
        """Splits the dataset into training,testing and validation data 
        Args:
            X (int),y (int) : size of the training dataset 
        Returns : 
            x_train,y_train,x_val,y_val,x_test,y_test
        """
        X_train, X_, y_train, y_ = train_test_split(X, y, train_size=self.TRAIN_SIZE, stratify=y)
        X_val, X_test, y_val, y_test = train_test_split(X_, y_, train_size=0.5, stratify=y_)
        return X_train, X_val, X_test, y_train, y_val, y_test

    def seq_padder(self,seq, mx_len=0):
        """
        Method to specify how much sequence padding is required
        Args:
            seq  (str) : The sequence to be paddded
            mx_len (int) :  How much max length to be considered while padding the sequences
        
        Returns:
            pd_seq [list]
        """
        mx_len = max(mx_len, max(len(s) for s in seq))
        pd_seq = np.zeros((len(seq), mx_len))
        for i, s in enumerate(seq):
            pd_seq[i][:len(s)] = s
        return pd_seq


    def last_relevant(self, hd_states, seq_lens):
        """
        Gathers last and the relavent data from the hidden states based on the
        sequence length provded
        
        Args:
            states : Hidden states
            seq_lens : Sequence length of the data
            
        Returns:
            res (tensor) : A sequence of combined tensors of new dimension
        """
        seq_lens = seq_lens.long().detach().cpu().numpy() - 1
        out = []
        for batch_index, column_index in enumerate(seq_lens):
            out.append(hd_states[batch_index, column_index])
        return torch.stack(out)




class lb_encoder(object):
    """Encodes each labels with  a tag label [basically each train labels will be encoded] and generates a json file as a result
    
    """
    def __init__(self, target_classes={}):
        """init function
        Args:
            target_classes (dict, required): _description_. Defaults to {}, this parameter will take the nos of classes 
                                            to be encoded along with the nos of items for each class types
        """
        self.target_classes = target_classes
        self.encoded_classes = {v: k for k, v in self.target_classes.items()}
        self.total_classes = list(self.target_classes.keys())

    def __len__(self):
        return len(self.target_classes)

    def __str__(self):
        return f"<lb_encoder{len(self)})>"

    def lb_fit(self, targets):
        """Encodes all the unique classes with their respective indices
        Args:
            targets (_type_): target classes to be encoded
        """
        total_classes = np.unique(targets)
        for i, class_ in enumerate(total_classes):
            self.target_classes[class_] = i
        self.encoded_classes = {v: k for k, v in self.target_classes.items()}
        self.total_classes = list(self.target_classes.keys())
        return self

    def lb_encode(self, targets):
        """One hot label  encoding  of the target class
        Args:
            targets (_type_): target classes to be encoded
        Returns:
            encoded_response: encoded class labels
        """
        encoded = np.zeros((len(targets)), dtype=int)
        for i, item in enumerate(targets):
            encoded[i] = self.target_classes[item]
        return encoded

    def lb_decode(self, targets):
        """Decodes the labelled classes 
        Args:
            targets (dict): encoded classes to be simplified
            
        Returns:
            response (list) : A list of decoded classes for the encoded labels passed
            """
        total_classes = []
        for i, item in enumerate(targets):
            total_classes.append(self.encoded_classes[item])
        return total_classes

    def save(self, filename):
        """Generates json file with label encoding 
        Args:
            filename (str): Name of the file
        """
        with open(filename, "w") as filename:
            contents = {'target_classes': self.target_classes}
            json.dump(contents, filename, indent=4, sort_keys=False)

    @classmethod
    def json_load(cls, filename):
        with open(filename, "r") as filename:
            kwargs = json.load(fp=filename)
        return cls(**kwargs)


class ct_tokenizer(object):
    def __init__(self, ch_lvl, nos_tkns=None,
                 pad_tkn="", oov_tkn="",
                 tkn_to_idx=None):
        """Initialize tokenizer
        Args:
            ch_lvl (boolean, optional): Enable character level tokenization or not. 
            nos_tkns (int, optional): Number of tokens . Defaults to None.
            pad_tkn (str, optional): Custom padding for the tokens . Defaults to "".
            oov_tkn (str, optional): Overriding the value of tokens . Defaults to "".
            tkn_to_idx (int, optional): Number of tokens to be converted to indexes. Defaults to None.
        """
        self.ch_lvl = ch_lvl
        self.sep = "" if self.ch_lvl else " "
        if nos_tkns: nos_tkns -= 2 # pad + unk tokens
        self.nos_tkns = nos_tkns
        self.pad_tkn = pad_tkn
        self.oov_tkn = oov_tkn
        if not tkn_to_idx:
            tkn_to_idx = {pad_tkn: 0, oov_tkn: 1}
        self.tkn_to_idx = tkn_to_idx
        self.idx_to_tkn = {v: k for k, v in self.tkn_to_idx.items()}

    def __len__(self):
        return len(self.tkn_to_idx)

    def __str__(self):
        return f"tokenizer_obj{len(self)})>"

    def fitter(self, texts):
        """
        Fits the tokens based on the txt being passed
        Args:
            txt (str) : The actual text being passed
        
        """
        if not self.ch_lvl:
            texts = [text.split(" ") for text in texts]
        all_tokens = [tkn for text in texts for tkn in text]
        counts = Counter(all_tokens).most_common(self.nos_tkns)
        self.min_token_freq = counts[-1][1]
        for tkn, count in counts:
            index = len(self)
            self.tkn_to_idx[tkn] = index
            self.idx_to_tkn[index] = tkn
        return self

    def txt_seq(self, texts):
        """Converts the texts to token sequences
        
        Args:
            txt (str) : The textual sequences
        
        Returns:
        token_seq (list)
        """
        sequences = []
        for text in texts:
            if not self.ch_lvl:
                text = text.split(" ")
            sequence = []
            for tkn in text:
                sequence.append(self.tkn_to_idx.get(
                    tkn, self.tkn_to_idx[self.oov_tkn]))
            sequences.append(np.asarray(sequence))
        return sequences

    def seq_txt(self, sequences):
        """converts the token sequences to texts
        Args:
            seq (str) : The textual sequences
        
        Returns: 
            Text (list)
        """
        texts = []
        for sequence in sequences:
            text = []
            for index in sequence:
                text.append(self.idx_to_tkn.get(index, self.oov_tkn))
            texts.append(self.sep.join([tkn for tkn in text]))
        return texts

    def save(self, filename):
        """
        Saves the tokenzied contents into a json dump
        Args:
            filename (str): Name of the file to load
        
        Returns:
            returns the json dumps
        """     
        with open(filename, "w") as filename:
            contents = {
                "ch_lvl": self.ch_lvl,
                "oov_tkn": self.oov_tkn,
                "tkn_to_idx": self.tkn_to_idx
            }
            json.dump(contents, filename, indent=4, sort_keys=False)

    @classmethod
    def load(cls, filename):
        """Loads the tokens from the given file
        Args:
            filename (str): Name of the file to load
        Returns:
            Keyworded_dictionary (dict) 
        """
        with open(filename, "r") as filename:
            kwargs = json.load(fp=filename)
        return cls(**kwargs)

class CustomDataSetManger(Dataset):
    """Generates custom tokenized preprocessed dataset
    """

    def __init__(self, X, y):
        self.tc_utils_class = TC_UTILS()
        self.X = X
        self.y = y

    def __len__(self):
        return len(self.y)

    def __str__(self):
        return f"{len(self)})>"

    def __getitem__(self, index):
        X = self.X[index]
        y = self.y[index]
        return [X, len(X), y]

    def collations(self, batch):
        """Preprocessing on a batch of dataset

        Args:
            data (ndarray): A batch of dataset in an array format
        """
        # Getting Input
        batch = np.array(batch)
        X = batch[:,0]
        seq_lens = batch[:, 1]
        y = batch[:, 2]

        # padding inputs
        X = self.tc_utils_class.seq_padder(seq=X) # max_seq_len=max_length

        # converting inputs to tensors
        X = torch.LongTensor(X.astype(np.int32))
        seq_lens = torch.LongTensor(seq_lens.astype(np.int32))
        y = torch.LongTensor(y.astype(np.int32))
        return X, seq_lens, y

    def create_datald(self, batch_size, shuffle=False, drop_last=False):
        dataloader = DataLoader(dataset=self, batch_size=batch_size, collate_fn=self.collations, shuffle=shuffle, drop_last=drop_last, pin_memory=True)
        return dataloader

