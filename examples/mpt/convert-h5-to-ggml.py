import sys
import struct
import json
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
import sentencepiece.sentencepiece_model_pb2 as model

if len(sys.argv) < 3:
    print("Usage: convert-h5-to-ggml.py dir-model [use-f32]\n")
    print("  ftype == 0 -> float32")
    print("  ftype == 1 -> float16")
    sys.exit(1)


# output in the same directory as the model
dir_model = sys.argv[1]
fname_out = sys.argv[1] + "/ggml-model.bin"


with open(dir_model + "/config.json", "r", encoding="utf-8") as f:
    hparams = json.load(f)

# possible data types
#   ftype == 0 -> float32
#   ftype == 1 -> float16
#
# map from ftype to string
ftype_str = ["f32", "f16"]

ftype = 1
if len(sys.argv) > 2:
    ftype = int(sys.argv[2])
    if ftype < 0 or ftype > 1:
        print("Invalid ftype: " + str(ftype))
        sys.exit(1)
    fname_out = sys.argv[1] + "/ggml-model-" + ftype_str[ftype] + ".bin"


tokenizer = AutoTokenizer.from_pretrained(dir_model, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    dir_model, low_cpu_mem_usage=True, trust_remote_code=True
)
# print (model)

# print(tokenizer.encode('I believe the meaning of life is'))

list_vars = model.state_dict()
for name in list_vars.keys():
    print(name, list_vars[name].shape, list_vars[name].dtype)

fout = open(fname_out, "wb")

print(hparams)

fout.write(struct.pack("i", 0x67676D6C))  # magic: ggml in hex
fout.write(struct.pack("i", hparams["d_model"]))
fout.write(struct.pack("i", hparams["max_seq_len"]))
fout.write(struct.pack("i", hparams["n_heads"]))
fout.write(struct.pack("i", hparams["n_layers"]))
fout.write(struct.pack("i", hparams["vocab_size"]))
fout.write(struct.pack("f", hparams["attn_config"]["alibi_bias_max"]))
fout.write(struct.pack("f", hparams["attn_config"]["clip_qkv"] or 0.0))
fout.write(struct.pack("i", ftype))


# TODO: temporary hack to not deal with implementing the tokenizer
dot_token = tokenizer.encode(".")[0]
for i in range(hparams["vocab_size"]):
    text = tokenizer.decode([dot_token, i]).encode("utf-8")
    # remove the first byte (it's always '.')
    text = text[1:]
    fout.write(struct.pack("i", len(text)))
    fout.write(text)

for name in list_vars.keys():
    data = list_vars[name].squeeze().numpy()
    print("Processing variable: " + name + " with shape: ", data.shape)

    n_dims = len(data.shape)

    # ftype == 0 -> float32, ftype == 1 -> float16
    ftype_cur = 0
    if ftype != 0:
        if name[-7:] == ".weight" and n_dims == 2:
            print("  Converting to float16")
            data = data.astype(np.float16)
            ftype_cur = 1
        else:
            print("  Converting to float32")
            data = data.astype(np.float32)
            ftype_cur = 0
    else:
        if data.dtype != np.float32:
            print("  Converting to float32")
            data = data.astype(np.float32)
            ftype_cur = 0

    # header
    str = name.encode("utf-8")
    fout.write(struct.pack("iii", n_dims, len(str), ftype_cur))
    for i in range(n_dims):
        fout.write(struct.pack("i", data.shape[n_dims - 1 - i]))
    fout.write(str)

    # data
    data.tofile(fout)

fout.close()

print("Done. Output file: " + fname_out)
print("")
