# Storage formats and conventions

## Data arrangement

The data intended to archive SHOULD first be grouped by type, and then sorted by time.

Data SHOULD be gathered in folders whose sizes are slightly less than a power of 2 to accommodate storage media sizes. The order of data is SHOULD to be slightly altered if it allows data to be packed more tightly. One MUST NOT split the data of a single entry even it contains multiple files, UNLESS there's a strong reason to do so, e.g. the storage media doesn't have enough size to hold it.

Optimal sizes for data grouping are:

- 15 MiB
- 30 MiB
- 61 MiB
- 122 MiB
- 244 MiB
- 488 MiB
- 976 MiB
- 1.86 GiB (1900 MiB)
- 3.72 GiB (3800 MiB)
- 7.45 GiB
- 14.9 GiB

Most data SHOULD be packed in 1.86 GiB or 3.72 GiB packs. Error correction code SHOULD be generated in a per group basis.

Data files larger than 2MiB each generally SHOULD NOT be packed together or compressed, as it increases the risk of corrupting the whole package. Data that contains many small files (e.g. source code tree with 1000 files and most are \<100KiB) MAY be packed together. Data files that are highly compressible (e.g. source code, again, or CSV data) MAY be packed and compressed before generating error correction code.

Data file MAY be encrypted before generating error correction code. The encryption method should be `AES-256-CBC`. The initialization vector should be copied into other disks in case the original one has corrupted.

PAR2 error correction code should be generated for every data group. Error code blocks should be spread into different disks and copies to increase redundancy. If the redundancy specified is `x%` and we are going to have `y` copies of data, the real redundancy set for PAR2 should be `x*y*2%`. Then, for each copy, we should put `x%` data along side the original disk and another `x%` spread into all other disks. One SHOULD NOT reuse error correction code.


## Storage type list

Data stored should be grouped into the types and subtypes below:

- Core (identities, passwords, private keys)
- 


## Storage format list

This is a list of storage formats that likely will continue to be supported in the future:

- Plaintext files
- Text formats
  - C and C++ code
  - Markdown
  - CSV
  - JSON
  - LaTeX
- Common compression formats
  - GZip
  - XZ
  - ZStandard
  - LZ4
- TAR
- Git bundle
- SQLite3
- Common Image formats
  - PNG
  - BMP
  - JPEG
  - JPEG-XL?
- MPEG-4
- PDF
- PAR2


## Storage mediums & data scrubs

Available storage mediums are:

- Hard drives
- Blu-ray disks

Storage media should be scrubbed regularly and recreated from other copies/correction data whenever they are corrupted or contains unrecoverable error in their data.

### Hard disks

Scrubbing a hard disk includes verifying all its data against hashes and checking the disk for bad sectors. If any recoverable data error was found, it should be recovered with redundant data, then the whole disk should be fully rewritten. If any bad sectors was found or the disk is over 10 years old, all the data should be transferred into a new disk.

Every half year, 1/4 of all the drives should be scrubbed.

### Optical disks

Scrubbing an optical disk is verifying all its data against hashes. If there's any error found in scrubbing, the whole disk should be read out, recovered with redundant data, and written into a new disk. The old disk should be thrown away.

Every half year, 1/4 of all the disks should be scrubbed.
