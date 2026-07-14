package com.example.courselingo.upload.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.upload.entity.UploadSession;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UploadSessionMapper extends BaseMapper<UploadSession> {

    default UploadSession selectByIdAndUserId(String id, Long userId) {
        return selectOne(Wrappers.<UploadSession>lambdaQuery()
            .eq(UploadSession::getId, id)
            .eq(UploadSession::getUserId, userId));
    }

    default int updateStatusByIdAndUserId(String id, Long userId, String status) {
        return update(Wrappers.<UploadSession>lambdaUpdate()
            .eq(UploadSession::getId, id)
            .eq(UploadSession::getUserId, userId)
            .set(UploadSession::getStatus, status));
    }
}
