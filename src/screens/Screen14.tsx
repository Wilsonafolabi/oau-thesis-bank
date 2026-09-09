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

const Screen14Upload = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Upload Research">
      <div className="max-w-3xl mx-auto">
        <UploadWizardNav step={1} />
        <Card className="p-12 text-center border-dashed border-2 border-slate-300 hover:border-[#00502F] transition-colors bg-slate-50">
          <FileUp className="w-16 h-16 mx-auto text-slate-400 mb-4" />
          <h3 className="text-xl font-semibold text-slate-900 mb-2">Drag and drop your thesis document</h3>
          <p className="text-slate-500 mb-6">Supported formats: PDF, DOCX (Max 50MB)</p>
          <div className="flex justify-center space-x-4">
            <Button onClick={() => navigate('thesis-metadata')}>Browse Files</Button>
          </div>
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen14Upload;
