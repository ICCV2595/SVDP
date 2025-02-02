import os.path as osp
import pickle
import shutil
import tempfile
import datetime

import mmcv
import numpy as np
import torch
import torch.distributed as dist
from torch.optim.lr_scheduler import StepLR
from mmcv.image import tensor2imgs
from mmcv.runner import get_dist_info
from mmcv.runner import build_optimizer, build_runner

from IPython import embed
from mmseg.ops import resize

import copy
import numpy as np
import kornia
import torch
import random
import torch.nn as nn
from mmseg.models.backbones.prompt import *
from mmseg.models.backbones.lora import *

import torch.nn.functional as F
IMG_MEAN = np.array((104.00698793, 116.66876762, 122.67891434), dtype=np.float32)
import pdb


def update_ema_variables_1(ema_model, model, alpha_teacher, iteration=None, dynamic_ema=False, anchor_student=None):
    # Use the "true" average until the exponential average is more correct
    if iteration:
        alpha_teacher = min(1 - 1 / (iteration + 1), alpha_teacher)

    param_list_low = []
    if dynamic_ema:
        weight_increment = []
        for student_all, anchor_student_para in zip(model.named_parameters(), anchor_student.parameters()):
            student_para = student_all[1]
            student_name = student_all[0]
            #print(student_name)
            weight_increment.append((torch.abs(student_para.data[:] - anchor_student_para.data[:]), student_name))


        cnt = 0
        while cnt < len(weight_increment):
            para, name = weight_increment[cnt]
            module_name = ''
            if 'attn' in name:
                module_name = name[:name.index('attn') + len('attn')]
            elif 'mlp' in name:
                module_name = name[:name.index('mlp') + len('mlp')]
            else:
                module_name = name[:name.rfind('.')]
            cnt += 1
            while module_name in weight_increment[cnt][1]:
                cnt += 1



        torch.set_printoptions(precision=10)
        print(weight_increment)

        weight_increment = sorted(weight_increment, key=lambda x:(x[0]))

        param_list_low = [x[1] for x in weight_increment[:(len(weight_increment) * 2 // 3)]]


    if True:
        for ema_param, named_param in zip(ema_model.parameters(), model.named_parameters()):
            #ema_param.data.mul_(alpha).add_(1 - alpha, param.data)
            name = named_param[0]
            param = named_param[1]
            if not dynamic_ema:
                ema_param.data[:] = alpha_teacher * ema_param[:].data[:] + (1 - alpha_teacher) * param[:].data[:]
            else:
                if name in param_list_low:
                    alpha_teacher = 0.999
                else:
                    alpha_teacher = 0.998
                ema_param.data[:] = alpha_teacher * ema_param[:].data[:] + (1 - alpha_teacher) * param[:].data[:]

    return ema_model


# def update_ema_variables(ema_model, model, alpha_teacher, iteration=None, dynamic_prompt_only=False, dynamic_ema=False, anchor_student=None, ema_rate_prompt=0.999):
#     # Use the "true" average until the exponential average is more correct
#     if iteration:
#         alpha_teacher = min(1 - 1 / (iteration + 1), alpha_teacher)

#     param_list_low = []
#     prompt_increment = None
#     if dynamic_prompt_only:
#         for student_all, anchor_student_para in zip(model.named_parameters(), anchor_student.parameters()):
#             student_para = student_all[1]
#             student_name = student_all[0]
#             if student_name == 'module.backbone.prompt.patch':
#                 prompt_increment = (torch.abs(student_para.data[:] - anchor_student_para.data[:]))
#         prompt_rank = []
#         for idx, grid in enumerate(prompt_increment):
#             prompt_rank.append((grid.mean(), idx))
#         prompt_rank = sorted(prompt_rank, key=lambda x:(x[0]))
#         lo_indices = [x[1] for x in prompt_rank[:len(prompt_rank) // 2]]

#     elif dynamic_ema:
#         weight_increment = []
#         for student_all, anchor_student_para in zip(model.named_parameters(), anchor_student.parameters()):
#             student_para = student_all[1]
#             student_name = student_all[0]
#             #print(student_name)
#             weight_increment.append((torch.abs(student_para.data[:] - anchor_student_para.data[:]), student_name))
#             if student_name == 'module.backbone.prompt.patch':
#                 prompt_increment = (torch.abs(student_para.data[:] - anchor_student_para.data[:]))

#         cnt = 0
#         while cnt < len(weight_increment):
#             para, name = weight_increment[cnt]
#             if 'weight' in name:
#                 mean_para = torch.numel(para) * para.mean()
#                 mean_total = torch.numel(para)
#                 weight_name = name
#                 weight_para = para.mean()
#                 module_name = name[:name.index('weight')]
#                 para, name = weight_increment[cnt + 1]
#                 if 'bias' in name and name[:name.index('bias')] == module_name:
#                     mean_para += torch.numel(para) * para.mean()
#                     mean_total += torch.numel(para)
#                     mean_para = mean_para / mean_total

#                     weight_increment[cnt] = (mean_para, weight_name)
#                     weight_increment[cnt + 1] = (mean_para, name)
#                     cnt += 2
#                     continue
#                 else:
#                     weight_increment[cnt] = (weight_para, weight_name)
#             else:
#                 weight_increment[cnt] = (para.mean(), name)
#             cnt += 1

#         # torch.set_printoptions(precision=10)
#         # print(prompt_increment.shape)
#         # print(prompt_increment)
#         weight_increment = sorted(weight_increment, key=lambda x:(x[0]))
#         param_list_low = [x[1] for x in weight_increment[:(len(weight_increment) * 1 // 10)]]
#         param_list_hi = [x[1] for x in weight_increment[(len(weight_increment) * 9 // 10):]]


    # if True:
    #     for ema_param, named_param in zip(ema_model.parameters(), model.named_parameters()):
    #         #ema_param.data.mul_(alpha).add_(1 - alpha, param.data)
    #         name = named_param[0]
    #         param = named_param[1]


    #         if dynamic_prompt_only and name == 'module.backbone.prompt.patch':
    #             for idx, grid in enumerate(param):
    #                 if idx in lo_indices:
    #                     alpha_teacher = 0.999
    #                 else:
    #                     alpha_teacher = 0.995
    #                 # print(f"size::: ema_param: {ema_param[idx].shape} ||| param: {param[idx].shape} ")
    #                 ema_param[idx].data[:] = alpha_teacher * ema_param[idx].data[:] + (1 - alpha_teacher) * param[idx].data[:]
    #         elif dynamic_prompt_only:
    #             continue
    #         elif dynamic_ema:
    #             if name in param_list_low:
    #                 alpha_teacher = 0.9995
    #                 #print('.',end='')
    #             elif name in param_list_hi:
    #                 alpha_teacher = 0.9988
    #             else:
    #                 alpha_teacher = 0.999
    #                 #print('|',end='')
    #             ema_param.data[:] = alpha_teacher * ema_param[:].data[:] + (1 - alpha_teacher) * param[:].data[:]
    #         else:
    #             # alpha_teacher = 0.999
    #             if ema_rate_prompt != 0.999:
    #                 if name == 'module.backbone.prompt.patch':
    #                     ema_param.data[:] = ema_rate_prompt * ema_param[:].data[:] + (1 - ema_rate_prompt) * param[:].data[:]
    #                     continue
    #             ema_param.data[:] = alpha_teacher * ema_param[:].data[:] + (1 - alpha_teacher) * param[:].data[:]


    # return ema_model



def update_ema_variables(ema_model, model, alpha_model, alpha_prompt, iteration=None):
    # Use the "true" average until the exponential average is more correct
    if iteration:
        alpha_teacher = min(1 - 1 / (iteration + 1), alpha_teacher)

    if True:
        for ema_param, (name, param) in zip(ema_model.parameters(), model.named_parameters()):
            #ema_param.data.mul_(alpha).add_(1 - alpha, param.data)
            if "prompt" in name:
                ema_param.data[:] = alpha_prompt * ema_param[:].data[:] + (1 - alpha_prompt) * param[:].data[:]
            else:
                ema_param.data[:] = alpha_model * ema_param[:].data[:] + (1 - alpha_model) * param[:].data[:]
    return ema_model

def np2tmp(array, temp_file_name=None):
    """Save ndarray to local numpy file.

    Args:
        array (ndarray): Ndarray to save.
        temp_file_name (str): Numpy file name. If 'temp_file_name=None', this
            function will generate a file name with tempfile.NamedTemporaryFile
            to save ndarray. Default: None.

    Returns:
        str: The numpy file name.
    """

    if temp_file_name is None:
        temp_file_name = tempfile.NamedTemporaryFile(
            suffix='.npy', delete=False).name
    np.save(temp_file_name, array)
    return temp_file_name

def softmax_entropy(x: torch.Tensor) -> torch.Tensor:
    """Entropy of softmax distribution from logits."""
    return -(x.softmax(1) * x.log_softmax(1)).sum(1)

def single_gpu_our(args,
                    model,
                    data_loader,
                    show=False,
                    out_dir=None,
                    efficient_test=False,
                    anchor=None,
                    ema_model=None,
                    anchor_model=None,
                    dynamic_ema=False,
                    dynamic_prompt_only=False,
                   ):
    """Test with single GPU.

    Args:
        model (nn.Module): Model to be tested.
        data_loader (utils.data.Dataloader): Pytorch data loader.
        show (bool): Whether show results during infernece. Default: False.
        out_dir (str, optional): If specified, the results will be dumped into
            the directory to save output results.
        efficient_test (bool): Whether save the results as local numpy files to
            save CPU memory during evaluation. Default: False.

    Returns:  
        list: The prediction results.
    """
    # model.eval()
    anchor_model.eval()
    results = []
    dataset = data_loader.dataset
    prog_bar = mmcv.ProgressBar(len(dataset))
    param_list = []
    param_list_1 = []

    # out_dir = "/data/ctta/cotta_vis/"+str(datetime.datetime.now())

    # out_dir = "./cotta/"+args.method+"_"+str(datetime.datetime.now())
    '''
    for name, param in model.named_parameters():
        if param.requires_grad and name == 'module.backbone.prompt.patch':
            param_list.append(param)
            print(name)
        else:
            param.requires_grad=False
    optimizer = torch.optim.Adam(param_list, lr=0.0001, betas=(0.9, 0.999))
    '''

    for name, param in model.named_parameters():
        #if param.requires_grad and name == 'module.backbone.prompt.patch':
        #if param.requires_grad:
        if param.requires_grad and "prompt" in name:
            param_list.append(param)
            print(name)
        elif param.requires_grad and "prompt" not in name:
            param_list_1.append(param)
        else:
            param.requires_grad=False
    optimizer = torch.optim.Adam([{"params": param_list, "lr": args.prompt_lr},
                                  {"params": param_list_1, "lr": args.model_lr}],
                                 lr=1e-5, betas=(0.9, 0.999)) #Batchsize=1 now, was 8 during cityscapes training
    #optimizer = torch.optim.Adam(param_list, lr=1e-4, betas=(0.9, 0.999))
    # psize = model.module.backbone.prompt.psize
    # pnum = model.module.backbone.prompt.num
    if args.tta_lr_decay:
        scheduler = StepLR(optimizer, step_size=args.tta_lr_decay_step, gamma=0.5)

    cnt = 0
    for i, data in enumerate(data_loader):
        cnt += 1
        '''
        print(">>>>>>>>>>>>>>>>>>>>>>>>>DDDDDDDDDD>>>>>>>>>>>")
        for t in data['img']:
            print(t.shape)
        print(">>>>>>>>>>>>>>>>>>>>>>>>>DDDDDDDDDD>>>>>>>>>>>")
        print(data['img'][0].shape)
        print(data['img'][0])
        '''
        model.eval()
        ema_model.eval()

        ema_model.module.decode_head.dropout = nn.Dropout(0.5)

        # 然后，即使模型处于评估模式，也可以单独激活这个 Dropout 层
        ema_model.module.decode_head.dropout.train()

        anchor_model.eval()
        # anchor_student = None
        # if dynamic_ema or dynamic_prompt_only:
        #     anchor_student = copy.deepcopy(model)
        with torch.no_grad():
            data_one = {
                'img_metas': [data['img_metas'][4] for i in range(1)],
                'img': [data['img'][4] for i in range(1)]
            }
            _, _, _, unc_all = ema_model(return_loss=False, svdp = True, dropout_num=10, **data_one)

            _, prob_anchor= anchor_model(return_loss=False, **data_one)

            # _, probs_, _ = anchor_model(return_loss=False, **data)
            mask = (prob_anchor[0] > 0.69).astype(np.int64) # 0.74 was the 5% quantile for cityscapes, therefore we use 0.69 here

            variance = np.var(unc_all, axis=0)
            uncertainty = np.sum(variance, axis=1)
            #print("???????????????????????????????????????????????????data", data['img'][4].shape)
            #print("???????????????????????????????????????????????????probs", probs_[4][0].shape)
            #print("???????????????????????????????????????????????????result", result)
            #for res in result:
            #    print("??????????????????", res.shape)
            model.module.backbone.prompt.if_mask = True
            model.module.backbone.prompt.update_uncmap(uncertainty[0])
            model.module.backbone.prompt.update_mask()

            ema_model.module.backbone.prompt.if_mask = True
            ema_model.module.backbone.prompt.update_uncmap(uncertainty[0])
            ema_model.module.backbone.prompt.update_mask()
            ema_model.eval()

            result, probs, preds = ema_model(return_loss=False,  **data)
            # ema_model.module.backbone.prompt.if_mask = False

            result = [(mask*preds[4][0] + (1.-mask)*result[0]).astype(np.int64)]
            # result = [(mask*preds[4][0] + (1.-mask)*result[0]).astype(np.int64)]
            weight = 1.
        # TODO! make sure consistence of img_tensor and loss result
        # TODO!! 14 image augmentation | alignment
        # if out_dir:
        #     #print("draw")
        #     #draw_map(probs_[4])

        #     img_tensor = data['img'][0]
        #     img_metas = data['img_metas'][0].data[0]
        #     prompt = SparsePrompterGrid_image(
        #         psize=args.prompt_psize, np_row=args.prompt_np_row, sparse_rate=args.prompt_sparse_rate)
        #     torch.no_grad()
        #     #img_tensor = prompt(img_tensor.cuda()).detach().cpu()
        #     img_tensor = img_tensor.detach().cpu()
        #     imgs = tensor2imgs(img_tensor, **img_metas[0]['img_norm_cfg'])
        #     assert len(imgs) == len(img_metas)
        #     for img, img_meta in zip(imgs, img_metas):
        #         h, w, _ = img_meta['img_shape']
        #         img_show = img[:h, :w, :]

        #         ori_h, ori_w = img_meta['ori_shape'][:-1]
        #         img_show = mmcv.imresize(img_show, (ori_w, ori_h))
        #         """
        #         $$$$$$$$$$$$$$$ img HW: 270 480 || origin HW: 1080 1920
        #         $$$$$$$$$$$$$$$ res shape: (1080, 1920)
        #         """
        #         if out_dir:
        #             out_file = osp.join(out_dir, img_meta['ori_filename'])
        #         else:
        #             out_file = None

        #         model.module.show_result(
        #             img_show,
        #             result,
        #             palette=dataset.PALETTE,
        #             show=show,
        #             out_file=out_file)
        if isinstance(result, list):
            if len(data['img']) == 14:
                img_id = 4 #The default size without flip 
            else:
                img_id = 0

            # print("img*************", data['img'][img_id])
            # print("imgmeta*************", data['img_metas'][img_id].data[0])
            loss = model.forward(return_loss=True, img=data['img'][img_id], img_metas=data['img_metas'][img_id].data[0], gt_semantic_seg=torch.from_numpy(result[0]).cuda().unsqueeze(0).unsqueeze(0))
            if efficient_test:
                result = [np2tmp(_) for _ in result]
            results.extend(result)
        else:
            if efficient_test:
                result = np2tmp(result)
            results.append(result)

        #print("????????????????????????????????loss", loss["decode.loss_seg"].shape)
        torch.mean(weight*loss["decode.loss_seg"]).backward()
        optimizer.step()
        optimizer.zero_grad()
        if args.tta_lr_decay:
            scheduler.step()
#         ema_model = update_ema_variables(
#             ema_model=ema_model, model=model, alpha_teacher=args.ema_rate, dynamic_prompt_only=dynamic_prompt_only, dynamic_ema=dynamic_ema, anchor_student=anchor_student, ema_rate_prompt=args.ema_rate_prompt
#         )
        prompt_rate = args.ema_rate - np.average(uncertainty) * args.scale

        ema_model = update_ema_variables(ema_model = ema_model, model = model, alpha_model=args.ema_rate, alpha_prompt = prompt_rate)
        for nm, m in model.named_modules():
            for npp, p in m.named_parameters():
                if npp in ['weight', 'bias'] and p.requires_grad:
                    mask = (torch.rand(p.shape)<0.01).float().cuda()
                    with torch.no_grad():
                        p.data = anchor[f"{nm}.{npp}"] * mask + p * (1.-mask)

        batch_size = data['img'][0].size(0)
        for _ in range(batch_size):
            prog_bar.update()
        # if i == args.num_img:
        #     return results
    return results



def single_gpu_tent(model,
                    data_loader,
                    show=False,
                    out_dir=None,
                    efficient_test=False):
    """Test with single GPU.

    Args:
        model (nn.Module): Model to be tested.
        data_loader (utils.data.Dataloader): Pytorch data loader.
        show (bool): Whether show results during infernece. Default: False.
        out_dir (str, optional): If specified, the results will be dumped into
            the directory to save output results.
        efficient_test (bool): Whether save the results as local numpy files to
            save CPU memory during evaluation. Default: False.

    Returns:
        list: The prediction results.
    """

    print('-------------model:::')
    print(model)
    model.eval()
    results = []
    dataset = data_loader.dataset
    prog_bar = mmcv.ProgressBar(len(dataset))
    param_list = []
    for name, param in model.named_parameters():
        if param.requires_grad:
            if param.requires_grad and ("norm" in name or "bn" in name):
                param_list.append(param)
                print(name)
            else:
                param.requires_grad=False

    optimizer = torch.optim.Adam(param_list, lr=0.00006/8, betas=(0.9, 0.999))
    for i, data in enumerate(data_loader):
        # print("--------------------------------data>>>>>>>>>>>>>>>>>>>>>>>>>")
        # print(data)

        with torch.no_grad():
            result = model(return_loss=False, **data)

        # print("--------------------------------data>>>>>>>>>>>>>>>>>>>>>>>>>")
        # print(data)

        if show or out_dir:
            img_tensor = data['img'][0]
            img_metas = data['img_metas'][0].data[0]
            imgs = tensor2imgs(img_tensor, **img_metas[0]['img_norm_cfg'])
            assert len(imgs) == len(img_metas)
            for img, img_meta in zip(imgs, img_metas):
                h, w, _ = img_meta['img_shape']
                img_show = img[:h, :w, :]

                ori_h, ori_w = img_meta['ori_shape'][:-1]
                img_show = mmcv.imresize(img_show, (ori_w, ori_h))

                if out_dir:
                    out_file = osp.join(out_dir, img_meta['ori_filename'])
                else:
                    out_file = None

                model.module.show_result(
                    img_show,
                    result,
                    palette=dataset.PALETTE,
                    show=show,
                    out_file=out_file)

        if isinstance(result, list):
            loss = model.forward(return_loss=True, img=data['img'][0], img_metas=data['img_metas'][0].data[0], gt_semantic_seg=torch.from_numpy(result[0]).cuda().unsqueeze(0).unsqueeze(0))
            if efficient_test:
                result = [np2tmp(_) for _ in result]
            results.extend(result)
        else:
            loss = model(return_loss=True, img=data['img'][0], img_metas=data['img_metas'][0].data[0], gt_semantic_seg=result)
            if efficient_test:
                result = np2tmp(result)
            results.append(result)

        torch.mean(loss["decode.loss_seg"]).backward()
        optimizer.step()
        optimizer.zero_grad()

        batch_size = data['img'][0].size(0)
        if i ==999:
            return results
        for _ in range(batch_size):
            prog_bar.update()
    return results



def single_gpu_test(args, 
                    model,
                    data_loader,
                    show=False,
                    out_dir=None,
                    efficient_test=False):
    """Test with single GPU.

    Args:
        model (nn.Module): Model to be tested.
        data_loader (utils.data.Dataloader): Pytorch data loader.
        show (bool): Whether show results during infernece. Default: False.
        out_dir (str, optional): If specified, the results will be dumped into
            the directory to save output results.
        efficient_test (bool): Whether save the results as local numpy files to
            save CPU memory during evaluation. Default: False.

    Returns:
        list: The prediction results.
    """

    model.eval()
    results = []
    dataset = data_loader.dataset
    prog_bar = mmcv.ProgressBar(len(dataset))
    out_dir = "./baseline/"+str(datetime.datetime.now())
    for i, data in enumerate(data_loader):
        with torch.no_grad():
            result = model(return_loss=False, **data)

        if show or out_dir:
            img_tensor = data['img'][0]
            img_metas = data['img_metas'][0].data[0]
            imgs = tensor2imgs(img_tensor, **img_metas[0]['img_norm_cfg'])
            assert len(imgs) == len(img_metas)

            for img, img_meta in zip(imgs, img_metas):
                h, w, _ = img_meta['img_shape']
                img_show = img[:h, :w, :]

                ori_h, ori_w = img_meta['ori_shape'][:-1]
                img_show = mmcv.imresize(img_show, (ori_w, ori_h))

                if out_dir:
                    out_file = osp.join(out_dir, img_meta['ori_filename'])
                else:
                    out_file = None

                model.module.show_result(
                    img_show,
                    result,
                    palette=dataset.PALETTE,
                    show=show,
                    out_file=out_file)

        if isinstance(result, list):
            if efficient_test:
                result = [np2tmp(_) for _ in result]
            results.extend(result)
        else:
            if efficient_test:
                result = np2tmp(result)
            results.append(result)

        batch_size = data['img'][0].size(0)
        if i == args.num_img:
            return results
        for _ in range(batch_size):
            prog_bar.update()
    return results


def multi_gpu_test(model,
                   data_loader,
                   tmpdir=None,
                   gpu_collect=False,
                   efficient_test=False):
    """Test model with multiple gpus.

    This method tests model with multiple gpus and collects the results
    under two different modes: gpu and cpu modes. By setting 'gpu_collect=True'
    it encodes results to gpu tensors and use gpu communication for results
    collection. On cpu mode it saves the results on different gpus to 'tmpdir'
    and collects them by the rank 0 worker.

    Args:
        model (nn.Module): Model to be tested.
        data_loader (utils.data.Dataloader): Pytorch data loader.
        tmpdir (str): Path of directory to save the temporary results from
            different gpus under cpu mode.
        gpu_collect (bool): Option to use either gpu or cpu to collect results.
        efficient_test (bool): Whether save the results as local numpy files to
            save CPU memory during evaluation. Default: False.

    Returns:
        list: The prediction results.
    """

    model.eval()
    results = []
    dataset = data_loader.dataset
    rank, world_size = get_dist_info()
    if rank == 0:
        prog_bar = mmcv.ProgressBar(len(dataset))
    for i, data in enumerate(data_loader):
        with torch.no_grad():
            result = model(return_loss=False, rescale=True, **data)

        if isinstance(result, list):
            if efficient_test:
                result = [np2tmp(_) for _ in result]
            results.extend(result)
        else:
            if efficient_test:
                result = np2tmp(result)
            results.append(result)

        if rank == 0:
            batch_size = data['img'][0].size(0)
            for _ in range(batch_size * world_size):
                prog_bar.update()

    # collect results from all ranks
    if gpu_collect:
        results = collect_results_gpu(results, len(dataset))
    else:
        results = collect_results_cpu(results, len(dataset), tmpdir)
    return results


def collect_results_cpu(result_part, size, tmpdir=None):
    """Collect results with CPU."""
    rank, world_size = get_dist_info()
    # create a tmp dir if it is not specified
    if tmpdir is None:
        MAX_LEN = 512
        # 32 is whitespace
        dir_tensor = torch.full((MAX_LEN, ),
                                32,
                                dtype=torch.uint8,
                                device='cuda')
        if rank == 0:
            tmpdir = tempfile.mkdtemp()
            tmpdir = torch.tensor(
                bytearray(tmpdir.encode()), dtype=torch.uint8, device='cuda')
            dir_tensor[:len(tmpdir)] = tmpdir
        dist.broadcast(dir_tensor, 0)
        tmpdir = dir_tensor.cpu().numpy().tobytes().decode().rstrip()
    else:
        mmcv.mkdir_or_exist(tmpdir)
    # dump the part result to the dir
    mmcv.dump(result_part, osp.join(tmpdir, 'part_{}.pkl'.format(rank)))
    dist.barrier()
    # collect all parts
    if rank != 0:
        return None
    else:
        # load results of all parts from tmp dir
        part_list = []
        for i in range(world_size):
            part_file = osp.join(tmpdir, 'part_{}.pkl'.format(i))
            part_list.append(mmcv.load(part_file))
        # sort the results
        ordered_results = []
        for res in zip(*part_list):
            ordered_results.extend(list(res))
        # the dataloader may pad some samples
        ordered_results = ordered_results[:size]
        # remove tmp dir
        shutil.rmtree(tmpdir)
        return ordered_results


def collect_results_gpu(result_part, size):
    """Collect results with GPU."""
    rank, world_size = get_dist_info()
    # dump result part to tensor with pickle
    part_tensor = torch.tensor(
        bytearray(pickle.dumps(result_part)), dtype=torch.uint8, device='cuda')
    # gather all result part tensor shape
    shape_tensor = torch.tensor(part_tensor.shape, device='cuda')
    shape_list = [shape_tensor.clone() for _ in range(world_size)]
    dist.all_gather(shape_list, shape_tensor)
    # padding result part tensor to max length
    shape_max = torch.tensor(shape_list).max()
    part_send = torch.zeros(shape_max, dtype=torch.uint8, device='cuda')
    part_send[:shape_tensor[0]] = part_tensor
    part_recv_list = [
        part_tensor.new_zeros(shape_max) for _ in range(world_size)
    ]
    # gather all result part
    dist.all_gather(part_recv_list, part_send)

    if rank == 0:
        part_list = []
        for recv, shape in zip(part_recv_list, shape_list):
            part_list.append(
                pickle.loads(recv[:shape[0]].cpu().numpy().tobytes()))
        # sort the results
        ordered_results = []
        for res in zip(*part_list):
            ordered_results.extend(list(res))
        # the dataloader may pad some samples
        ordered_results = ordered_results[:size]
        return ordered_results

import time
import cv2
def draw_map(x):
    tic=time.time()
    name = str(tic)
    H=1080 // 2
    W=1920 // 2
    x_visualize = x
    print('ssssssssssss',x.shape)

    x_visualize =  x_visualize[0]
    x_visualize = (((x_visualize - np.min(x_visualize))/(np.max(x_visualize)-np.min(x_visualize)))*255).astype(np.uint8) #归一化并映射到0-255的整数，方便伪彩色化
    savedir = './cotta/uncer/'
    import os
    if not os.path.exists(savedir+'dense'):
        os.mkdir(savedir+'dense')
    x_visualize = cv2.applyColorMap(x_visualize, cv2.COLORMAP_WINTER)  # 伪彩色处理
    cv2.imwrite(savedir+'dense/'+name+'.jpg',x_visualize) #保存可视化图像