# Yuunagi

Yuunagi (夕凪) is a collection of tools used in my personal archiving procedure.

Yuunagi is created for my DataArchive2022 project, which includes saving data on hard disks and blu-ray disks.

## Archive procedure

The data being archived goes through 4 states until they finally reside on the archive media. The 4 states are:

- **Raw data**. The data is already organized (done beforehand), but not indexed or compressed.
- **Data packs**. The data has been indexed and put into variable-sized packs (may be compressed or encrypted, depending on data property). For data that does not need to be changed in this stage, they are simply organized virtually without moving on disk. 
- **Data blocks**. The data is organized in larger (several GiBs in size), near-fixed-sized blocks that roughly follows natural data order (time or alphabetic, depending on the task). This step is fully virtual - nothing is moved on disk.
  - **Parity data**. Parity files are generated for every data pack inside the data block.
- **Storage media**. The data, data index, readme files, checksums and utility tools are copied into the target storage media.

## Tools

Yuunagi is built with Unix philosophy in mind. Each tool in Yuunagi is complete and serves a single purpose inside the archiving procedure. Higher order tools call these tools to implement more complex behavior.

| Tool              | Status   | Purpose                                                   |
| ----------------- | -------- | --------------------------------------------------------- |
| `encrypt-archive` | Working  | Archive creation (with digests and encryption)            |
| `index-data`      | WIP      | Identify data packs and create an index for later use     |
| `binpack`         | Thinking | Decide which data pack go to which blocks                 |
| `manage-disk`     | Thinking | Distribute data blocks and parity data into storage media |
| `create-iso`      | Thinking | Create ISO from what `manage-disk` has decided on         |

## License

WTFPL. These tools are made for _my_ own needs, so feel free to fiddle with these tools to fit _your_ own needs.
