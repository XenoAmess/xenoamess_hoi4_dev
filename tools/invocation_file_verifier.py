"""Reuse actual byte reads only inside one bounded, sole-writer verification."""
from pathlib import Path
from tools.common import file_sha256


class InvocationFileVerifier:
    def __init__(self):
        self._verified={}
        self.full_reads=0
        self.reuses=0
        self.bytes_fully_read=0

    @staticmethod
    def version(path):
        st=path.stat()
        return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

    def __call__(self,path):
        path=Path(path).resolve()
        before=self.version(path)
        previous=self._verified.get(path)
        if previous and previous[0]==before:
            self.reuses+=1
            return previous[1]
        digest=file_sha256(path)
        if self.version(path)!=before:
            raise ValueError('File changed during complete byte verification: '+str(path))
        self._verified[path]=(before,digest)
        self.full_reads+=1
        self.bytes_fully_read+=before[2]
        return digest

    def summary(self):
        return {'full_byte_reads':self.full_reads,'unchanged_same_invocation_reuses':self.reuses,
                'bytes_fully_read':self.bytes_fully_read,'scope':'Process-local only. Every reused digest came from complete bytes read in this checkpoint and unchanged device/inode/size/mtime/ctime. No persisted checksum cache or remote-byte proof.'}
