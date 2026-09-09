import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen26GapDetail = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Gap Analysis">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="flex items-center space-x-2 text-slate-500 hover:text-slate-800 cursor-pointer mb-2" onClick={() => navigate('gap-explorer')}>
          <ArrowLeft className="w-4 h-4" /> <span>Back to Gaps</span>
        </div>
        
        <div>
          <Badge variant="gold" className="mb-3">Identified Potential Gap</Badge>
          <h2 className="text-3xl font-bold text-slate-900 leading-tight">Lack of Offline Capabilities in AI/ML Solutions for Rural Environments</h2>
        </div>

        <Card className="p-6 bg-[#F8F9FA] border-none">
          <h3 className="font-semibold text-slate-900 flex items-center mb-3"><FileSearch className="w-5 h-5 mr-2 text-[#00502F]"/> AI Evidence Synthesis</h3>
          <p className="text-slate-700 text-sm leading-relaxed">
            Across 24 recent theses in Computer Science and Agricultural Engineering, researchers successfully built predictive models (disease detection, market pricing). However, 85% of these projects noted in their 'Limitations' section that their solutions require constant internet connectivity, rendering them unusable for target end-users (rural farmers) in Osun State.
          </p>
        </Card>

        <div>
          <h3 className="text-xl font-semibold text-slate-900 mb-4">Theses Citing This Limitation</h3>
          <div className="space-y-4">
            {[1, 2].map((i) => (
              <div key={i} className="p-4 border border-slate-200 rounded-lg bg-white">
                <h4 className="font-medium text-[#00502F] cursor-pointer hover:underline mb-2" onClick={() => navigate('thesis-detail')}>Deep Learning Approaches for Early Plant Disease Detection (2024)</h4>
                <div className="bg-red-50 border-l-4 border-red-400 p-3 text-sm text-slate-700 italic">
                  "A major limitation of the developed mobile application is its reliance on cloud-based API calls for inference. Future work should explore model compression to allow the application to run purely on the edge device in remote farms." - Page 82
                </div>
              </div>
            ))}
          </div>
        </div>
        
        <div className="flex justify-center pt-6">
          <Button onClick={() => navigate('upload')}><PlusCircle className="w-4 h-4 mr-2"/> Start a Project in this Area</Button>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen26GapDetail;
