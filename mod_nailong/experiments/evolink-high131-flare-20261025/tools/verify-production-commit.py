import sys,os,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,write_json,machine_id,utc_now
from mod_nailong.tools import master_git_remote
from runtime.high131_tree_cache import install_local_tree_cache


def scoped_readback_checkpoint():
    configured = os.environ.get('XAR_READBACK_CHECKPOINT')
    if not configured:
        return None
    candidate = (ROOT / configured).resolve()
    candidate.relative_to((ROOT / 'runtime').resolve())
    if candidate == master_git_remote.CHECKPOINT:
        raise ValueError('Scoped readback must not replace the shared checkpoint pointer')
    if not candidate.exists() and master_git_remote.CHECKPOINT.is_file():
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(master_git_remote.CHECKPOINT.read_bytes())
    return candidate


def main():
    scoped = scoped_readback_checkpoint()
    if scoped is not None:
        master_git_remote.CHECKPOINT = scoped
    commit,batch=sys.argv[1:3]
    receipt={'machine_id':machine_id(),'commit':commit,'started_at_utc':utc_now(),'process_id':os.getpid(),'status':'running'}
    out=ROOT/f'runtime/master-readback-{batch}.json';write_json(out,receipt)
    lock=ROOT/'runtime/master-git-readback.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode('ascii'));os.close(fd)
    try:
        local_tree_cache=install_local_tree_cache()
        result=master_git_remote.verify_remote(commit)
        receipt.update(status='verified',distinct_outputs=result['distinct_outputs'],original_png_bytes=result['original_png_bytes'],completed_at_utc=utc_now())
        if local_tree_cache is not None:
            receipt['local_tree_cache']=local_tree_cache
    except BaseException:
        receipt.update(status='failed',error=traceback.format_exc(),completed_at_utc=utc_now());raise
    finally:
        write_json(out,receipt);lock.unlink()


if __name__=='__main__':
    main()
