"""Create only this evaluation's topic/group over the broker protocol; no docker exec."""
import json
import socket
import struct
from runtime_support import *


def request(code,fields=None,body=None):
    assert code in (17,21,200,201)
    header=json.dumps(dict(code=code,language='PYTHON',version=433,opaque=21016,flag=0,extFields=fields or {}),separators=(',',':')).encode()
    payload=struct.pack('>I',len(header))+header+(json.dumps(body).encode() if body is not None else b'')
    with socket.create_connection(('127.0.0.1',20911),timeout=10) as sock:
        sock.sendall(struct.pack('>I',len(payload))+payload)
        def read(n):
            out=b''
            while len(out)<n:
                chunk=sock.recv(n-len(out))
                if not chunk:raise RuntimeError('BROKER_CONNECTION_CLOSED')
                out+=chunk
            return out
        data=read(struct.unpack('>I',read(4))[0])
    size=struct.unpack('>I',data[:4])[0]
    assert size>>24==0
    size &= 0xffffff
    result=json.loads(data[4:4+size])
    assert result['code']==0, str(result)
    return result,json.loads(data[4+size:]) if data[4+size:] else None


if __name__=='__main__':
    guard()
    _,topics=request(21)
    _,groups=request(201)
    assert TOPIC not in topics['topicConfigTable'],'Evaluation topic already exists'
    group=TOPIC+'-consumer'
    assert group not in groups['subscriptionGroupTable'],'Evaluation group already exists'
    topic_result,_=request(17,dict(topic=TOPIC,defaultTopic='TBW102',readQueueNums='4',writeQueueNums='4',perm='6',topicFilterType='SINGLE_TAG',topicSysFlag='0',order='false',attributes='+message.type=NORMAL'))
    group_result,_=request(200,body=dict(groupName=group,consumeEnable=True,consumeFromMinEnable=True,consumeBroadcastEnable=False,retryQueueNums=1,retryMaxTimes=16,brokerId=0,whichBrokerWhenConsumeSlowly=1,notifyConsumerIdsChangedEnable=True,consumeTimeoutMinute=15))
    _,after_topics=request(21);_,after_groups=request(201)
    save(PUBLIC/'mq-preparation.json',dict(utc=utc(),broker='127.0.0.1:20911',topic=after_topics['topicConfigTable'][TOPIC],consumer_group=after_groups['subscriptionGroupTable'][group],topic_response=topic_result['code'],group_response=group_result['code'],existing_topics_unchanged=all(after_topics['topicConfigTable'][k]==v for k,v in topics['topicConfigTable'].items()),existing_groups_unchanged=all(after_groups['subscriptionGroupTable'][k]==v for k,v in groups['subscriptionGroupTable'].items()),container_operations=0))
    print('P21_MQ_PREPARATION_PASS')
