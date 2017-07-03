#!/bin/bash
        for i in `6 seq  20`;
        do
                echo $i
                python3  single_run.py $i >> test_emb.log
        done  